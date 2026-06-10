from aws_cdk import Duration, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from constructs import Construct


class CdnStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        alb: elbv2.ApplicationLoadBalancer,
        certificate: acm.ICertificate,
        hosted_zone: route53.IHostedZone,
        domain_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        html_cache_policy = cloudfront.CachePolicy(
            self, "HtmlCachePolicy",
            cache_policy_name="GhostHtmlCache",
            default_ttl=Duration.minutes(10),
            min_ttl=Duration.seconds(0),
            max_ttl=Duration.minutes(10),
            enable_accept_encoding_gzip=True,
            enable_accept_encoding_brotli=True,
        )

        static_cache_policy = cloudfront.CachePolicy(
            self, "StaticCachePolicy",
            cache_policy_name="GhostStaticCache",
            default_ttl=Duration.days(365),
            min_ttl=Duration.days(1),
            max_ttl=Duration.days(365),
            enable_accept_encoding_gzip=True,
            enable_accept_encoding_brotli=True,
        )

        # HTTP to ALB avoids the SSL cert mismatch: the ALB cert is for the
        # custom domain, not the ALB hostname. CloudFront cannot verify it.
        # HTTPS is enforced at the viewer level by viewer_protocol_policy below.
        alb_origin = origins.LoadBalancerV2Origin(
            alb,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            http_port=80,
        )

        # Forward the viewer's Host header so Ghost receives the custom domain name
        # rather than the ALB hostname. Without this Ghost redirects every request.
        all_viewer_policy = cloudfront.OriginRequestPolicy.from_origin_request_policy_id(
            self, "AllViewerPolicy", "216adef6-5c7f-47e4-b989-5492eafa07d3"
        )

        self.distribution = cloudfront.Distribution(
            self, "Distribution",
            domain_names=[domain_name],
            certificate=certificate,
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            default_behavior=cloudfront.BehaviorOptions(
                origin=alb_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=html_cache_policy,
                origin_request_policy=all_viewer_policy,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                compress=True,
            ),
            additional_behaviors={
                # Ghost admin and API — never cache, forward all headers and cookies
                "/ghost/*": cloudfront.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=all_viewer_policy,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    compress=False,
                ),
                # Theme static assets — long cache
                "/assets/*": cloudfront.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=static_cache_policy,
                    compress=True,
                ),
                # Ghost media uploads — long cache
                "/content/images/*": cloudfront.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=static_cache_policy,
                    compress=True,
                ),
            },
        )

        # Apex A + AAAA alias records pointing to CloudFront
        route53.ARecord(
            self, "AliasRecord",
            zone=hosted_zone,
            target=route53.RecordTarget.from_alias(
                targets.CloudFrontTarget(self.distribution)
            ),
        )
        route53.AaaaRecord(
            self, "AaaaRecord",
            zone=hosted_zone,
            target=route53.RecordTarget.from_alias(
                targets.CloudFrontTarget(self.distribution)
            ),
        )
