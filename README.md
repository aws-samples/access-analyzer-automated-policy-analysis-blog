# Automating IAM Access Analyzer custom policy checks

As covered in the following blog post: https://aws.amazon.com/blogs/security/introducing-iam-access-analyzer-custom-policy-checks/ 

> [!IMPORTANT]  
> AWS has extended custom policy checks to include a new check called Check No Public Access. This new check determines whether a resource policy grants public access to a specified resource type. In addition to this new check, there has been an update to the existing Check Access Not Granted check. The Check Access Not Granted check can now be used to determine whether a given policy grants permission to one or more customer-defined AWS resources. This example has been updated to include these new checks.

In this example, you will automate the validation and analysis of the IAM identity and resources policies that are defined in an AWS CloudFromation template. The workflow will trigger each time a pull request is created against the main branch of an AWS CodeCommit repository called my-iam-policy. The workflow includes 3 checks. The first check will use IAM Access Analyzer's check no new access API to determine if the updated policy is more permissive than a reference IAM policy. The second check will use the check access not granted API to automatically check for critical permissions in an IAM policy. The third check uses the CheckNoPublicAccess API to check whether a resource policy grants public access to supported resource types. In all cases, if the updated policy is more permissive, contains sensitive permissions or grants public access to a sensitive resource type, a comment with the results of the validation will be posted to the pull request. This information can then be used to decide whether or not the pull request is merged in to the mainline for deployment.

![Custom IAM Policy Analysis Reference Archiecture](/static/policy_analysis_ref_arch.jpg "Reference Architecture")

### Step 1: Deploy the infrastructure and set up the pipeline

1. Use the following command to create a local clone of the Cloud Development Kit (CDK) project associated with this example.

    ```
    git clone https://github.com/aws-samples/access-analyzer-automated-policy-analysis-blog.git
    cd ./access-analyzer-automated-policy-analysis-blog
    ```
    
2. Create a virtual Python environment to contain the project dependencies by using the following command.

    ```
    python3 -m venv .venv
    ```

3. Activate the virtual environment with the following command.

    ```
    source .venv/bin/activate
    ```

4. Install the project requirements by using the following command.

    ```
    pip install -r requirements.txt
    ```

5. Use the following command to update the CDK CLI to the latest major version.

    ```
    npm install -g aws-cdk@2 --force
    ```

6. Before you can deploy the CDK project, use the following command to bootstrap your AWS environment. Bootstrapping is the process of creating resources needed for deploying CDK projects. These resources include an Amazon Simple Storage Service (Amazon S3) bucket for storing files and IAM roles that grant permissions needed to perform deployments.

    ```
    cdk bootstrap
    ```

7. Finally, use the following command to deploy the pipeline infrastructure.

    ```
    cdk deploy --require-approval never
    ```

The deployment will take a few minutes to complete. Feel free to grab a coffee and check back shortly.

When the deployment completes, there will be two stack outputs listed: one with a name that contains CodeCommitRepo and another with a name that contains ConfigBucket. Make a note of the values of these outputs, because you will need them later.

8. Use the following command to create the reference policy. 

    ```
    cd ../
    cat << EOF > cnna-reference-policy.json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "*",
                "Resource": "*"
            },
            {
                "Effect": "Deny",
                "Action": "iam:PassRole",
                "Resource": "arn:aws:iam::*:role/my-sensitive-roles/*"
            }
        ]
    }	
    EOF
    ```

9. Use the following command to create a list of sensitive actions. This list will be parsed during the build pipeline and passed to the CheckAccessNotGranted API. If the policy grants access to one or more of the sensitive actions in this list, a result of FAIL will be returned. To keep this example simple, add a single API action, as follows. 

    ```
    cat << EOF > sensitive-actions.file
    dynamodb:DeleteTable
    EOF
    ```

10. So that the CodeBuild projects can access the dependencies, use the following command to copy the cnna-reference-policy.file and sensitive-actions.file to an S3 bucket. Refer to the stack outputs you noted earlier and replace <ConfigBucket> with the name of the S3 bucket created in your environment. 

    ```
    aws s3 cp ./cnna-reference-policy.json s3://<ConfgBucket>/cnna-reference-policy.json
    aws s3 cp ./sensitive-actions.file s3://<ConfigBucket>/sensitive-actions.file
    ```

### Step 2: Create a new CloudFormation template that defines an IAM policy

With the pipeline deployed, the next step is to clone the repository that was created and populate it with a CloudFormation template that defines an IAM policy.

1. Install git-remote-codecommit by using the following command.

    ```
    pip install git-remote-codecommit
    ```

For more information on installing and configuring git-remote-codecommit, see the AWS CodeCommit User Guide.

2. With git-remote-codecommit installed, use the following command to clone the my-iam-policy repository from AWS CodeCommit.

    ```
    git clone codecommit://my-iam-policy && cd ./my-iam-policy
    ```

If you’ve configured a named profile for use with the AWS CLI, use the following command, replacing <profile> with the name of your named profile.

    git clone codecommit://<profile>@my-iam-policy && cd ./my-iam-policy

> [!CAUTION]
> This example CloudFormation templates in the following sections should not be used in production. They are intended to be used for demonstration purposes only.

3. Use the following command to create the CloudFormation template in the local clone of the repository. 

    ```yaml
    cat << EOF > ec2-instance-role.yaml
    ---
    AWSTemplateFormatVersion: 2010-09-09
    Description: CloudFormation Template to deploy base resources for access_analyzer_blog
    Resources:
      EC2Role:
        Type: AWS::IAM::Role
        Properties:
          AssumeRolePolicyDocument:
            Version: 2012-10-17
            Statement:
            - Effect: Allow
              Principal:
                Service: ec2.amazonaws.com
              Action: sts:AssumeRole
          Path: /
          Policies:
          - PolicyName: my-application-permissions
            PolicyDocument:
              Version: 2012-10-17
              Statement:
              - Effect: Allow
                Action:
                  - 'ec2:RunInstances'
                  - 'lambda:CreateFunction'
                  - 'lambda:InvokeFunction'
                  - 'dynamodb:Scan'
                  - 'dynamodb:Query'
                  - 'dynamodb:UpdateItem'
                  - 'dynamodb:GetItem'
                Resource: '*'
              - Effect: Allow
                Action:
                  - iam:PassRole 
                Resource: "arn:aws:iam::*:role/my-custom-role"
            
      EC2InstanceProfile:
        Type: AWS::IAM::InstanceProfile
        Properties:
          Path: /
          Roles:
            - !Ref EC2Role
    EOF
    ```
The actions in the IAMPolicyValidation stage are run by a CodeBuild project. CodeBuild environments run arbitrary commands that are passed to the project using a buildspec file. Each project has already been configured to use an inline buildspec file.

### Step 3: Run analysis on the IAM policy

The next step involves checking in the first version of the CloudFormation template to the repository and checking two things. First, that the policy does not grant more access than the reference policy. Second, that the policy does not contain any of the sensitive actions defined in the sensitive-actions.file.

1. To begin tracking the CloudFormation template created earlier, use the following command.

    ```
    git add ec2-instance-role.yaml
    ```

2. Commit the changes you have made to the repository.

    ```
    git commit -m 'committing a new CFN template with IAM policy'
    ```

3. Finally, push these changes to the remote repository.

    ```
    git push
    ```

4. Pushing these changes will initiate the pipeline. After a few minutes the pipeline should complete successfully. To view the status of the pipeline, do the following:

    - Navigate to https://*{region}*.console.aws.amazon.com/codesuite/codepipeline/pipelines (replacing *{region}* with your AWS Region).
    - Choose the pipeline called accessanalyzer-pipeline.
    - Scroll down to the IAMPolicyValidation stage of the pipeline.
    - For both the check no new access and check access not granted actions, choose View Logs to inspect the log output.

5. If you inspect the build logs for both the **check-no-new-access**, **check-access-not-granted** and **check-no-public-access** actions within the pipeline, you should see that there were no blocking or non-blocking findings. This indicates that the policy was checked successfully. In other words, the policy was not more permissive than the reference policy, it did not include any of the critical permissions or resources and there were no resources that were public.

### Step 4: Create a pull request to merge a new update to the CloudFormation template

In this step, you will make a change to the IAM policy in the CloudFormation template. The change deliberately makes the policy grant more access than the reference policy. The change also includes a critical permission and makes makes and adds a secrets manager secret with a resource policy that permits public access. 

1. Use the following command to create a new branch called add-new-permissions in the local clone of the repository.

    ```
    git checkout -b add-new-permissions
    ```

2. Next, edit the IAM policy in ec2-instance-role.yaml to include an additional API action, dynamodb:Delete*, update the resource property of the inline policy to use an IAM role in the /my-sensitive-roles/*” path anf finally add a new Secrets Manager Secret that has resource policy that grants public access to the secret. You can copy the following example, if you’re unsure of how to do this. 

    ```yaml
    cat << EOF > ec2-instance-role.yaml
    ---
    AWSTemplateFormatVersion: 2010-09-09
    Description: CloudFormation Template to deploy base resources for access_analyzer_blog
    Resources:
      EC2Role:
        Type: AWS::IAM::Role
        Properties:
          AssumeRolePolicyDocument:
            Version: 2012-10-17
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Path: /
          Policies:
          - PolicyName: my-application-permissions
            PolicyDocument:
              Version: 2012-10-17
              Statement:
                - Effect: Allow
                  Action:
                    - 'ec2:RunInstances'
                    - 'lambda:CreateFunction'
                    - 'lambda:InvokeFunction'
                    - 'dynamodb:Scan'
                    - 'dynamodb:Query'
                    - 'dynamodb:UpdateItem'
                    - 'dynamodb:GetItem'
                    - 'dynamodb:Delete*'
                  Resource: '*'
                - Effect: Allow
                  Action:
                    - iam:PassRole 
                  Resource: "arn:aws:iam::*:role/my-sensitive-roles/my-custom-admin-role"
            
      EC2InstanceProfile:
        Type: AWS::IAM::InstanceProfile
        Properties:
          Path: /
          Roles:
            - !Ref EC2Role

      MySecret:
        Type: AWS::SecretsManager::Secret
        Properties:
         Description: This is a secret that I want to attach a resource-based policy to
    
      MySecretResourcePolicy:
        Type: AWS::SecretsManager::ResourcePolicy
        Properties:
          SecretId:
            Ref: MySecret
          ResourcePolicy:
            Version: '2012-10-17'
            Statement:
            - Sid: "DenyAllAccountDeleteSecret"
              Resource: "*"
              Action: secretsmanager:DeleteSecret
              Effect: Deny
              Principal: "*"
            - Sid: "AllowAllAccountGetSecretValue"
              Resource: "*"
              Action: secretsmanager:GetSecretValue
              Effect: Allow
              Principal: "*"
    EOF
    ```

3. Commit the policy change and push the updated policy document to the repo by using the following commands. 

    ```
    git add ec2-instance-role.yaml 
    git commit -m "adding new permission and allowing my ec2 instance to assume a pass sensitive IAM role"
    ```

4. The add-new-permissions branch is currently a local branch. Use the following command to push the branch to the remote repository. This action will not initiate the pipeline, because the pipeline only runs when changes are made to the repository’s main branch. 

    ```
    git push -u origin add-new-permissions
    ```

5. With the new branch and changes pushed to the repository, follow these steps to create a pull request:

    - Navigate to https://console.aws.amazon.com/codesuite/codecommit/repositories (don’t forget to the switch to the correct Region).
    - Choose the repository called **my-iam-policy**.
    - Choose the branch add-new-permissions from the drop-down list at the top of the repository screen.
    - Choose **Create pull request**.
    - Enter a title and description for the pull request.
    - (Optional) Scroll down to see the differences between the current version and new version of the CloudFormation template highlighted.
    - Choose **Create pull request**.

6. The creation of the pull request will Initiate the pipeline to fetch the CloudFormation template from the repository and run the check no new access and check access not granted analysis actions.

7. After a few minutes, choose the Activity tab for the pull request. You should see a comment from the pipeline that contains the results of the failed validation. 

### Why did the validations fail?

The updated IAM role and inline policy failed validation for three reasons. First, the reference policy said that no one should have more permissions than the reference policy does. The reference policy in this example included a deny statement for the iam:PassRole permission with a resource of /my-sensitive-role/*. The new created inline policy included an allow statement for the iam:PassRole permission with a resource of arn:aws:iam::*:role/my-sensitive-roles/my-custom-admin-role. In other words, the new policy had more permissions than the reference policy.

Second, the list of critical permissions included the dynamodb:DeleteTable permission. The inline policy included a statement that would allow the EC2 instance to perform the dynamodb:DeleteTable action.

Third and finally, the newly create Secrets Manager Secret had resource policy that grants public access to the secret.

### Cleanup

Use the following command to delete the infrastructure that was provisioned as part of the examples in this blog post.

    cdk destroy
    