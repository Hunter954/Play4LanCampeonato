import os, boto3

def upload_fileobj(fileobj,key):
    bucket=os.getenv('S3_BUCKET')
    if not bucket: return None
    c=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT_URL') or None,region_name=os.getenv('S3_REGION') or None,aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID'),aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY'))
    c.upload_fileobj(fileobj,bucket,key)
    return key

def presigned_download(key,expires=3600):
    bucket=os.getenv('S3_BUCKET')
    if not bucket: return None
    c=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT_URL') or None,region_name=os.getenv('S3_REGION') or None,aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID'),aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY'))
    return c.generate_presigned_url('get_object',Params={'Bucket':bucket,'Key':key},ExpiresIn=expires)
