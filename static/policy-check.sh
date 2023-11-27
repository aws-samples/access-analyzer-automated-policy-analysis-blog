cnnaReviewFindings=$(cfn-policy-validator check-if-less-permissive --template-path *.yaml --reference-policy control-policy.json --reference-policy-type identity --region us-west-2)
cnnaResult=$(echo $cnnaReviewFindings | jq -r '.BlockingFindings[].details.result')
if [ $cnnaResult == 'PASS' ];
then 
  echo "Policy validation completed successfully"
  echo -------------
  echo -------------
elif [ $cnnaResult == 'FAIL' ];
then
  cnnaReason=$(echo $cnnaReviewFindings | jq -r '.BlockingFindings[].details.result'')
  echo "Policy validation failed: $cnnaReason"
  echo -------------
  echo -------------
  exit 1
fi