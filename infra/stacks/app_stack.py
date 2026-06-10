from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class AppStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        vpc: ec2.Vpc,
        repository: ecr.Repository,
        db_instance: rds.DatabaseInstance,
        hosted_zone: route53.IHostedZone,
        domain_name: str,
        image_tag: str = "latest",
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # S3 bucket for Ghost media uploads
        self.media_bucket = s3.Bucket(
            self, "MediaBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            versioned=False,
        )

        # ACM certificate for the ALB — eu-west-2, DNS validated via Route 53
        alb_certificate = acm.Certificate(
            self, "AlbCertificate",
            domain_name=domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # ECS Cluster
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        # Execution role: ECS infrastructure (pull image, write logs, read SSM secrets)
        execution_role = iam.Role(
            self, "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )

        # Task role: Ghost application (S3 read/write)
        task_role = iam.Role(
            self, "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        self.media_bucket.grant_read_write(task_role)

        # SSM parameter references — values resolved by ECS at task start, not at synth time
        ghost_url_param = ssm.StringParameter.from_string_parameter_name(
            self, "GhostUrlParam", "/ghost/url"
        )
        db_password_param = ssm.StringParameter.from_string_parameter_name(
            self, "DbPasswordParam", "/ghost/database/password"
        )

        ghost_url_param.grant_read(execution_role)
        db_password_param.grant_read(execution_role)

        # Task definition
        task_def = ecs.FargateTaskDefinition(
            self, "TaskDef",
            cpu=512,
            memory_limit_mib=1024,
            task_role=task_role,
            execution_role=execution_role,
        )

        container = task_def.add_container(
            "ghost",
            image=ecs.ContainerImage.from_ecr_repository(repository, tag=image_tag),
            environment={
                "NODE_ENV": "production",
                "database__client": "mysql",
                "database__connection__database": "ghost",
                "database__connection__user": "ghost",
                "database__connection__host": db_instance.db_instance_endpoint_address,
                "database__connection__port": "3306",
                "storage__active": "s3",
                "storage__s3__region": self.region,
                "storage__s3__bucket": self.media_bucket.bucket_name,
            },
            secrets={
                "url": ecs.Secret.from_ssm_parameter(ghost_url_param),
                "database__connection__password": ecs.Secret.from_ssm_parameter(db_password_param),
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ghost",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "kill -0 1 2>/dev/null || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )
        container.add_port_mappings(ecs.PortMapping(container_port=2368))

        # Security groups
        alb_sg = ec2.SecurityGroup(
            self, "AlbSg",
            vpc=vpc,
            description="Ghost ALB",
        )
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv6(), ec2.Port.tcp(443))
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv6(), ec2.Port.tcp(80))

        ecs_sg = ec2.SecurityGroup(
            self, "EcsSg",
            vpc=vpc,
            description="Ghost ECS tasks",
        )
        ecs_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(2368))

        # ALB
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "Alb",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        target_group = elbv2.ApplicationTargetGroup(
            self, "TargetGroup",
            vpc=vpc,
            port=2368,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/",
                healthy_http_codes="200-399",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(10),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
            ),
        )

        self.alb.add_listener(
            "HttpsListener",
            port=443,
            certificates=[elbv2.ListenerCertificate.from_certificate_manager(alb_certificate)],
            default_target_groups=[target_group],
        )

        # HTTP listener forwards to Ghost — CloudFront is the HTTPS terminator.
        # Redirect would loop: CloudFront→HTTP→ALB 301→CloudFront→HTTP→ALB 301…
        self.alb.add_listener(
            "HttpListener",
            port=80,
            default_target_groups=[target_group],
        )

        # ECS Service — public subnets, assign_public_ip so tasks can reach ECR without NAT
        self.service = ecs.FargateService(
            self, "GhostService",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            assign_public_ip=True,
            # Stop old task before starting new one; fine for dev single-task service
            min_healthy_percent=0,
            max_healthy_percent=100,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=False),
        )
        self.service.attach_to_application_target_group(target_group)

        repository.grant_pull(execution_role)
