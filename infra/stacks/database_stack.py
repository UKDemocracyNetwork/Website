from aws_cdk import (
    CfnDynamicReference,
    CfnDynamicReferenceService,
    Duration,
    RemovalPolicy,
    SecretValue,
    Stack,
)
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from constructs import Construct


class DatabaseStack(Stack):
    def __init__(self, scope: Construct, id: str, *, vpc: ec2.Vpc, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.db_security_group = ec2.SecurityGroup(
            self,
            "DbSecurityGroup",
            vpc=vpc,
            description="Ghost RDS MySQL",
            allow_all_outbound=False,
        )
        # Allow MySQL from anything in the VPC. RDS is in isolated subnets with no internet
        # route, so only VPC-internal resources (ECS tasks) can reach it in practice.
        self.db_security_group.add_ingress_rule(
            ec2.Peer.ipv4(vpc.vpc_cidr_block),
            ec2.Port.tcp(3306),
        )

        # Password resolved from SSM at CloudFormation deploy time via dynamic reference.
        # new_env.py must write /ghost/database/password before cdk deploy is run.
        self.instance = rds.DatabaseInstance(
            self,
            "GhostDb",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G,
                ec2.InstanceSize.MICRO,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[self.db_security_group],
            database_name="ghost",
            credentials=rds.Credentials.from_password(
                username="ghost",
                password=SecretValue.cfn_dynamic_reference(
                    CfnDynamicReference(
                        CfnDynamicReferenceService.SSM,
                        "/ghost/database/password",
                    )
                ),
            ),
            multi_az=False,
            allocated_storage=20,
            storage_type=rds.StorageType.GP3,
            backup_retention=Duration.days(1),
            delete_automated_backups=True,
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
            publicly_accessible=False,
        )
