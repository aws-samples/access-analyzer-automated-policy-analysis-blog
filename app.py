#!/usr/bin/env python3
import os
import yaml
import aws_cdk as cdk
from aws_cdk import Aspects
from cdk_nag import AwsSolutionsChecks

from access_analyzer_blog.access_analyzer_stack import AccessAnalyzerStack

with open("./config.yaml") as stream:
    config = yaml.safe_load(stream)

app = cdk.App()
AccessAnalyzerStack(app, "AccessAnalyzerStack", config)

Aspects.of(app).add(AwsSolutionsChecks(verbose=False))

app.synth()
