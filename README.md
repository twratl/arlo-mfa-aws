# Arlo MFA

## Overall
This solution is designed to allow the continued automated use of Arlo cameras/accessories.
Specifically this is meant to be plugged into https://github.com/jeffreydwalter/arlo.

Arlo has announced that MFA will be a requirement for all new accounts effectively immediately and all existing accounts by the end of 2020. Therefore a solution has to be developed which can handle this MFA requirement.
In an ideal world Arlo would either allow users to opt out of MFA (option 1) or at least offer a OTP option (option 2) instead of just SMS, email, or push notifications.
If an OTP option existed then `pyotp` could easily solve this MFA issue.
In the absence of option 1 or 2 this solution is being offered as an option 3. 

This solution allows for a multi-user approach should that be desirable. It however does not require a multi-user approach.
You are welcome to spin this up in your own dedicated AWS account and have it be 100% for you and you alone.

This solution does not store any sensitive information. 

* All email addresses are hashed via SHA256 before being persisted
* All data stores use server side encryption
* No Lambda logging occurs, outside of the standard START,END,REPORT logs (you will have to add debug statements if you which to send additional logs for testing)
* No data stores are publicly accessible (AWS credentials are required for all access to data stores) 

This solution comes with no unit tests or guarantees. It was built to solve a need I had and I offer it up to the community for use and enhancement.


## Prerequisites
### DNS
* You need to own a domain already - I simply created a subdomain off of mine called mfa.domain.com
* Verify your (sub)domain for incoming email using the SES console
* Set up MX record on your (sub)domain for sending emails to inbound-smtp.[region].amazonaws.com with a priority of 10 (valid regions are us-east-1, us-west-2, eu-west-1)

### Email provider
* Set up a rule with your email provider (whatever email address you use to login to Arlo) to forward emails that match the Arlo MFA email (from do_not_reply@arlo.com, has the words "Your Arlo one-time authentication code is") to your already defined Arlo MFA email address you will be using for this solution

### Arlo
* You will likely want to create an Arlo account dedicated to this purpose and then share your cameras/etc. with this account

### AWS
* You will need an AWS account for this solution
* Some knowledge of AWS is preferred - many of the concepts and much of the terminology will be meaningless unless you have some base AWS knowledge
* Be prepared to spend > $0. It won't be much but is also won't be entirely free. See the Estimated Costs section for further details
* You are not already using SES incoming email since this solution will set the active receipt rule set to the one it created - which could impact any existing receipt rule sets you already have (you can always use a different AWS region as well)
* An S3 bucket (with some type of default encryption preferred) that `sam` will use to store deployment artifacts

## Estimated Costs
Costs will be calculated at a rate of logging into Arlo (with MFA) 1 time per hour. 
That is 24 times a day * 30 days in a month = 720 invocations per month.

All costs assume you are out of the AWS Free Tier (12 month free tier - some services are forever free tier).

AWS Free Tier: https://aws.amazon.com/free/

* AWS Lambda will be free for this effort (unless you share your deployment with others) as you get 1 million free invocations per month https://aws.amazon.com/lambda/pricing/
* HTTP API Gateway - there will be minimal cost - less than $1/month based on $1/million HTTP API requests per month https://aws.amazon.com/api-gateway/pricing/
* S3 pricing will be less than $1/month https://aws.amazon.com/s3/pricing/
* DynamoDB pricing will be free as you get 25 RCU and WCU free forever per month https://aws.amazon.com/dynamodb/pricing/provisioned/
* SES Incoming Email should be free as the first 1000 per month are free https://aws.amazon.com/ses/pricing/
* CloudWatch Logs should be free at 5GB/month free forever

In total, this solution should cost well less than $1/month unless you offer it as a shared service or it is being abused.

As always, SET UP A BILLING ALERT IN THE BILLING CONSOLE WHEN YOU FORECASTED COSTS GO ABOVE $1/$2/$3 A MONTH OR WHATEVER THRESHOLD YOU WANT. 

This solution is provided as-is. You are fully responsible for any and all costs incurred by using this solution.

## Pre Deployment
* You will need the AWS CLI 
* You will need credentials for the AWS CLI (don't use root user credentials please)
* You will need `sam` for deployment https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html

## Deployment
* Simply run `./deploy.sh <region> <stack> <forward-to-email> <s3-bucket-for-sam-artifacts>` and the solution will be deployed

Example

~~~bash
./deploy.sh us-east-1 arlo-mfa arlo@mfa.domain.com s3-bucket-name-for-sam-artifacts
~~~

## Post Deployment
* In the SES console, manually make the receipt rule set the active one
* Set up an CloudWatch alarms you want to alert you when this solution is being invoked more often than you think it should be (to help alert to cost increases and potential abuse)

## Deleting the Stack
* Empty the S3 bucket (so the stack successfully deletes)
* Set the SES receipt rule set to inactive (or the stack will not fully delete)


## How To Use After Deployment
The goal is to add some additional code to https://github.com/jeffreydwalter/arlo.

Before initiating the login sequence a call is made to the HTTPS endpoint generated by this solution which will "pre stage" the email address that will be forwarding the Arlo MFA code.
The response of this call will be a presigned S3 URL which you will poll every 1-3 seconds waiting for a `status` of `complete`.
Before starting the polling you will log into Arlo with your username/password and if MFA is required, start polling the S3 presigned url since Arlo will initiate the out-of-band EMAIL MFA process.
Once the `complete` status is attained you can extract the MFA code from the response and provide it to Arlo via the Arlo API call.

To use this solution the `arlo.py` file will need to be updated in the arlo package hosted at https://github.com/jeffreydwalter/arlo

Some of the code was pulled from https://github.com/m0urs/arlo-cl as well and adapted for this use.


Add an import...
~~~python
import requests as standard_requests
~~~


Modify `__init__`
~~~python
    def __init__(self, username, password, mfa_prestage_url=None):

        # signals only work in main thread
        try:
            signal.signal(signal.SIGINT, self.interrupt_handler)
        except:
            pass

        self.event_streams = {}
        self.request = None

        self.Login(username, password, mfa_prestage_url)
~~~

Modify `Login`. Note that I also modified it to accept non base64 encoded passwords and it will
do the encoding for us.
~~~python
    def Login(self, username, password, mfa_prestage_url=None):
        self.username = username
        self.password = str(base64.b64encode(password.encode("utf-8")), "utf-8")
        self.mfa_prestage_url = mfa_prestage_url

        self.request = Request()

        print('getting auth token')

        # Get authorization token
        body = self.request.post('https://ocapi-app.arlo.com/api/auth',
                                 {'email': self.username, 'password': self.password, "language": "en",
                                  "EnvSource": "prod"}, self.createHeaders())
        token = body['token']
        token_base64 = str(base64.b64encode(token.encode("utf-8")), "utf-8")

        # Check if 2FA enabled
        if body["mfa"] and self.mfa_prestage_url:
            print('trying to get mfa')
            # Get a list of all valid two factors
            body = self.request.get(
                'https://ocapi-app.arlo.com/api/getFactors?data%20=%20' + str(body['authenticated']), {},
                self.createHeaders(token_base64))
            factors = body['items']

            # Get the two factor ID for EMAIL MFA option
            factor = list(filter(lambda factors: factors['factorType'] == 'EMAIL', factors))[0]


            #remove the email label if one exists, since the email will not be forwarded with the label intact
            username, domain = factor['displayName'].split('@')
            username = username.split('+')[0]
            email = '{}@{}'.format(username, domain)
            print('prestaging with email {}'.format(email))
            
            # perform the pre-stage process with the AWS serverless app
            mfa_url = standard_requests.post(
                self.mfa_prestage_url,
                json={'email': email}
            ).text


            # deliver the code to the second factor (email in this case)
            body = self.request.post(
                'https://ocapi-app.arlo.com/api/startAuth',
                {"factorId": factor['factorId']},
                self.createHeaders(token_base64)
            )

            # poll and wait for the otp code to show up
            otp = None
            while True:
                response = standard_requests.get(mfa_url).json()
                status = response['status']
                if status == 'pending':
                    print('still waiting for the code - sleeping 1 second')
                    time.sleep(1)
                    continue
                if status == 'error':
                    print(response['message'])
                    return
                if status == 'complete':
                    otp = response['code']
                    print(otp)
                    break


            # Finish 2FA and get new authorization token
            body = self.request.post(
                'https://ocapi-app.arlo.com/api/finishAuth',
                {"factorAuthCode": body['factorAuthCode'], "otp": otp},
                self.createHeaders(token_base64)
            )
            token = body['token']
            token_base64 = str(base64.b64encode(token.encode("utf-8")), "utf-8")
        else:
            print('no MFA required')

        # Verifiy authorization token
        body = self.request.get('https://ocapi-app.arlo.com/api/validateAccessToken?data = {}'.format(int(time.time())),
                                {}, self.createHeaders(token_base64))

        # Open session
        body = self.request.get('https://my.arlo.com/hmsweb/users/session/v2', {}, self.createHeaders(token))

        self.user_id = body['userId']
        self.token = body['token']
        self.headers = self.createHeaders(token)

        return body
~~~

And in your application code you do the following to create the `Arlo` object and then proceed as normal
with the rest of your application logic
~~~python
arlo = Arlo(USERNAME, PASSWORD, MFA_PRESTAGE_URL)  #password is NOT base64 encoded
~~~


## Todo
* add automated deployment via github hooks (negating the need for a development environment)
* add CloudWatch alarms via CloudFormation
* Have the CICD pipeline make the receipt rule set the active one automatically