import base64
import boto3
import os
from hashlib import sha256
import json
import time
import uuid


ddb = boto3.resource('dynamodb')
table = ddb.Table(os.environ['table'])
s3 = boto3.resource('s3')
bucket = os.environ['bucket']


def get_data(event):
    is_b64 = event.get('isBase64Encoded', False)
    body = event.get('body')
    if not body:
        raise Exception('body not found')
    decoded_body = body
    if is_b64:
        decoded_body = base64.b64decode(body)
    data = json.loads(decoded_body)

    if 'email' not in data.keys():
        raise Exception('parameter [email] not found')

    return data


def add_to_dynamo(data):
    table.put_item(
        Item={
            'hashed_email': sha256(data['email'].encode('utf-8')).hexdigest(),
            'uuid': data['uuid'],
            'expires_at': int(time.time()) + 3600  # expire dynamo records after an hour as they become worthless
        }
    )


def create_s3_object(uuid):
    s3_object = s3.Object(bucket, 'codes/{}'.format(uuid))
    body = {
        'status': 'pending'
    }
    s3_object.put(Body=json.dumps(body))
    url = s3.meta.client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': bucket,
            'Key': 'codes/{}'.format(uuid)
        },
        ExpiresIn=300  # expire the presigned url in 5 minutes - at that point the MFA code is worthless anyway
    )
    return url


def handler(event, context):
    response = {
        'statusCode': 200
    }
    try:
        data = get_data(event)
        data['uuid'] = uuid.uuid4().hex
        add_to_dynamo(data)
        url = create_s3_object(data['uuid'])
        body = {
            'status': 'pending'
        }
        response['body'] = url
    except Exception as e:
        response['statusCode'] = 500
        response['body'] = str(e)

    return response

