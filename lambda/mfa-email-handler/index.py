

# grab return path from the event
# grab the message id and then get the s3 object email from the bucket
# parse the email using the email package
# extract the html version of the email (as plain text doesnt seem to exist in the Arlo MFA email)
# regex the html body to extract the MFA code
# look up the UUID for the given sender
# write the MFA code to the UUID object in S3

import boto3
import os
import email
from email import policy  # https://stackoverflow.com/questions/45124127/unable-to-extract-the-body-of-the-email-file-in-python/48101684
import re
from hashlib import sha256
from boto3.dynamodb.conditions import Key
import json


s3 = boto3.resource('s3')
bucket = os.environ['bucket']
ddb = boto3.resource('dynamodb')
table = ddb.Table(os.environ['table'])


def get_sender(record):
    """
    gmail auto forwarding messes with the source address by adding a crazy label
    so we are parsing that out - it shouldn't negatively impact other addresses
    """
    source = record['ses']['mail']['source']
    address, domain = source.split('@')
    name, label = address.split('+')
    return '{}@{}'.format(name, domain)


def get_message_id(record):
    return record['ses']['mail']['messageId']


def parse_email(message_id):
    contents = s3.Object(bucket, 'emails/{}'.format(message_id)).get()['Body'].read().decode('utf-8')
    return email.message_from_string(contents, policy=policy.default)


def get_code(mfa_email):
    html = mfa_email.get_body(preferencelist=('html'))
    code = re.search(r"\s(\d{6})\s", str(html)).group(1)
    return code


def get_uuid(sender):
    items = table.query(
        KeyConditionExpression=Key('hashed_email').eq(sha256(sender.encode('utf-8')).hexdigest())
    )['Items']

    if len(items) == 0:
        raise Exception('sender not found')
    if len(items) > 1:
        raise Exception('too many items found for sender')
    return items[0]['uuid']


def update_s3_object(uuid, code, error_message=None):
    s3_object = s3.Object(bucket, 'codes/{}'.format(uuid))

    if code == 'error':
        body = {
            'status': 'error',
            'message': error_message
        }
    else:
        body = {
            'status': 'complete',
            'code': code
        }

    s3_object.put(Body=json.dumps(body))


def process(record):
    # if these first 2 things don't work we cannot update the s3 object anyway so they live outside the try block
    sender = get_sender(record)
    uuid = get_uuid(sender)
    try:
        message_id = get_message_id(record)
        mfa_email = parse_email(message_id)
        code = get_code(mfa_email)
        update_s3_object(uuid, code)
    except Exception as e:
        update_s3_object(uuid, 'error', str(e))


def handler(event, context):
    for record in event['Records']:
        try:
            process(record)
        except Exception as e:  # just catch an error for the given record so we don't halt processing of other records
            print(e)
