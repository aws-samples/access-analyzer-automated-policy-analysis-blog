from constructs import Construct
import aws_cdk as cdk
from cdk_nag import NagSuppressions, NagPackSuppression
from aws_cdk import (
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_codebuild as codebuild,
    aws_lambda as awslambda,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_iam as iam
)

class Pipeline(Construct):

    def __init__(self, scope: Construct, id: str, devtools, config: dict, **kwargs):
        super().__init__(scope, id, **kwargs)

        ### CodePipeline
        pipeline = codepipeline.Pipeline(
            self, "Pipeline",
            pipeline_name="accessanalyzer-pipeline",
            stages=[]
        )

        ### Define source Stage
        source_output = codepipeline.Artifact()
        pipeline.add_stage(
            stage_name="CheckoutSource",
            actions=[
                codepipeline_actions.CodeCommitSourceAction(
                    action_name="CodeCommit",
                    branch="main",
                    repository=devtools.code_repo,
                    output=source_output,
                    run_order=1
                )
            ]
        )

        ### IAM policy analysis stage
        security_ci = pipeline.add_stage(
            stage_name="IAMPolicyAnalysis"
        )

        ### Define check no new access action
        cnna = codebuild.PipelineProject(
            self, "CNNA",
            project_name="codebuild-cnna-project",
            build_spec=codebuild.BuildSpec.from_asset("./static/cnna_buildspec.yaml"),
            environment=codebuild.BuildEnvironment(
                privileged=False,
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3
            ),
                environment_variables={
                "CNNA_PERIMETER": codebuild.BuildEnvironmentVariable(
                    value="s3://" + devtools.config_bucket.bucket_name + "/cnna-reference-policy.json"
                )
            },
            description="Check No New Access",
            timeout=cdk.Duration.minutes(60)
        )

        cnna.role.attach_inline_policy(iam.Policy(self, "CNNAInlinePolicy",
            document=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement( 
                        actions=[
                            "access-analyzer:ListAnalyzers",
                            "access-analyzer:ValidatePolicy",
                            "access-analyzer:CreateAccessPreview",
                            "access-analyzer:GetAccessPreview",
                            "access-analyzer:ListAccessPreviewFindings",
                            "access-analyzer:CreateAnalyzer",
                            "access-analyzer:CheckAccessNotGranted",
                            "access-analyzer:CheckNoNewAccess"
                        ],
                        resources=["*"]
                    ), 
                    iam.PolicyStatement( 
                        actions=["s3:getObject"], 
                        resources=[
                            devtools.config_bucket.bucket_arn,
                            devtools.config_bucket.bucket_arn+"/*"
                        ]
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "codecommit:PostCommentForPullRequest",
                            "codecommit:UpdatePullRequestStatus", 
                            "codecommit:GitPull"
                        ],
                        resources=[devtools.code_repo.repository_arn]
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "iam:GetPolicy",
                            "iam:GetPolicyVersion"
                        ],
                        resources=["*"]
                    ) 
                ]
            ) 
        ))

        security_ci.add_action(
            codepipeline_actions.CodeBuildAction(
                action_name="Check-no-new-access",
                input=source_output,
                project=cnna,
                run_order=2
            )
        )

        ### Define check access not granted action
        cang = codebuild.PipelineProject(
            self, "CANG",
            project_name="codebuild-cang-project",
            build_spec=codebuild.BuildSpec.from_asset("./static/cang_buildspec.yaml"),
            environment=codebuild.BuildEnvironment(
                privileged=False,
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3
            ),
            environment_variables={
                "CANG_PERIMETER": codebuild.BuildEnvironmentVariable(
                    value="s3://" + devtools.config_bucket.bucket_name + "/sensitive-actions.file"
                )
            },
            description="Check Access Not Granted",
            timeout=cdk.Duration.minutes(60)
        )

        ### Define role permissions for check access not granted action
        cang.role.attach_inline_policy(iam.Policy(self, "CANGInlinePolicy",
            document=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement( 
                        actions=[
                            "access-analyzer:ListAnalyzers",
                            "access-analyzer:ValidatePolicy",
                            "access-analyzer:CreateAccessPreview",
                            "access-analyzer:GetAccessPreview",
                            "access-analyzer:ListAccessPreviewFindings",
                            "access-analyzer:CreateAnalyzer",
                            "access-analyzer:CheckAccessNotGranted",
                            "access-analyzer:CheckNoNewAccess"
                        ],
                        resources=["*"]
                    ), 
                    iam.PolicyStatement( 
                        actions=["s3:getObject"], 
                        resources=[
                            devtools.config_bucket.bucket_arn,
                            devtools.config_bucket.bucket_arn+"/*"
                        ]
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "codecommit:PostCommentForPullRequest", 
                            "codecommit:UpdatePullRequestStatus", 
                            "codecommit:GitPull" 
                        ],
                        resources=[devtools.code_repo.repository_arn]
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "iam:GetPolicy",
                            "iam:GetPolicyVersion"
                        ],
                        resources=["*"]
                    )  
                ] 
            ) 
        ))

        ### Add check access not granted action to pipeline
        security_ci.add_action(
            codepipeline_actions.CodeBuildAction(
                action_name="Check-access-not-granted",
                input=source_output,
                project=cang,
                run_order=2
            )
        )

        ## Add deploy stage to Pipeline
        pipeline.add_stage( 
            stage_name="Deploy",
            actions=[codepipeline_actions.CloudFormationCreateUpdateStackAction(
                action_name="Deploy",
                stack_name=devtools.code_repo.repository_name,
                template_path=source_output.at_path("ec2-instance-role.yaml"),
                admin_permissions=True
            )])
        
        # Add event bridge rule to trigger codepipline based on pull request 
        rule = events.Rule( 
            self, "PullRequestEvent",
            description="Trigger Pipeline on Pull Request",
            event_pattern=events.EventPattern(
                source=["aws.codecommit"],
                detail_type=["CodeCommit Pull Request State Change"],
                resources=[devtools.code_repo.repository_arn],
                detail={ 
                    "destinationReference": ["refs/heads/main"],
                    "event": ["pullRequestCreated"]
                    }
                )
        )

        ### Define lambda function to trigger pipeline based on event bridge rule
        lambda_function = awslambda.Function(
            self, "TargetForPullRequests",
            code=awslambda.Code.from_asset("./static/lambda_function"),
            handler="lambda_function.lambda_handler",
            runtime=awslambda.Runtime.PYTHON_3_11,
            environment={
                "CNNA_PROJECT_NAME": cnna.project_name,
                "CANG_PROJECT_NAME": cang.project_name
            }
        )

        ### Define role permissions for Lambda function
        lambda_function.add_to_role_policy(iam.PolicyStatement(
            actions=["codebuild:StartBuild"],
            resources=[cnna.project_arn, cang.project_arn]
        ))

        NagSuppressions.add_resource_suppressions(lambda_function,[{
            'id': 'AwsSolutions-IAM4', 'reason': 'supressing since it only allows your lambda permissions to write logs'
        }],apply_to_children=True,)

        rule.add_target(events_targets.LambdaFunction(lambda_function))
