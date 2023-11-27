from constructs import Construct
import aws_cdk as cdk
import cdk_nag

from .devtools import DevTools
from .pipeline import Pipeline


class AccessAnalyzerStack(cdk.Stack):

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        ### CDK Constructs for the Developer Tools
        devtools = DevTools(self, "DevTools", config)

        ### CDK Constructs for the DevSecOps Pipeline
        pipeline = Pipeline(self, "Pipeline", devtools, config)

        # Adding CDK Nag stack suppressions
        cdk_nag.NagSuppressions.add_stack_suppressions(
            self, 
            suppressions=[
                {"id": "AwsSolutions-IAM5", "reason": "Default CDK permissions"},
                {"id": "AwsSolutions-IAM4", "reason": "Default CDK permissions"},
                {"id": "AwsSolutions-S1", "reason": "This is a non-production stack and uses the default CDK configurations. These configurations are suitable for sample code because this environment should not run for extended periods of time without customer specific configurations applied."},
                {"id": "AwsSolutions-KMS5", "reason": "This is a non-production stack and uses default CDK configurations. These configuraitons are suitable for sample code because this environment should not run for extended periods of time without customer specific configurations applied."}
            ])
        
        # Adding CDK Nag resource level suppressions
        cdk_nag.NagSuppressions.add_resource_suppressions_by_path(
            self,
            path=f"{self.stack_name}/Pipeline/CANGInlinePolicy/Resource",
            suppressions=[
                cdk_nag.NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason="Required for access analyzer to work",
                    applies_to=["Resource::*"]
                )
                ,
                cdk_nag.NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason="Required for CodeBuild to access artifacts at non-deterministic paths in S3",
                    applies_to=["Resource::<DevToolsPipelineConfigBucket94C0C0B6.Arn>/*"]
                ),
            ]
        ) 

        cdk_nag.NagSuppressions.add_resource_suppressions_by_path(
            self,
            path=f"{self.stack_name}/Pipeline/CNNAInlinePolicy/Resource",
            suppressions=[
                cdk_nag.NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason="Required for access analyzer to work",
                    applies_to=["Resource::*"]
                ),
                cdk_nag.NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason="Required for CodeBuild to access artifacts at non-deterministic paths in S3",
                    applies_to=["Resource::<DevToolsPipelineConfigBucket94C0C0B6.Arn>/*"]
                ),
            ]
        )
        
