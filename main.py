"""
This script creates projects in Label Studio, creates buckets in S3 object storage and binds them to projects.
Project described in `config.yaml` file, credentials described in `credentials.yaml` file.
"""

import yaml
import yandexcloud
from label_studio_sdk.client import LabelStudio
from yandex.cloud.storage.v1.bucket_pb2 import CorsRule, VERSIONING_DISABLED
from yandex.cloud.storage.v1.bucket_service_pb2 import ListBucketsRequest, CreateBucketRequest, \
    UpdateBucketRequest
from yandex.cloud.storage.v1.bucket_service_pb2_grpc import BucketServiceStub


def _load_yaml(file_path: str):
    """
    Load yaml file by path
    """
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)


def _create_projects(config, credentials):
    """
    Create projects in Label Studio, create buckets in S3 object storage and bind them to projects

    :param config: configuration file with details of the project
    :param credentials: credentials file with secrets to access Label Studio and S3 object storage
    """
    client = _client(config, credentials)
    for project_draft in config['projects']:
        details = project_draft['details']
        # Create or update project
        title = details.get('title')
        if not title:
            raise ValueError('Project title is required')
        if ls_project := _find_project_by_title(title, client):
            ls_project = client.projects.update(ls_project.id, **details)
            print(f"Updated project: {ls_project.dict()}")
        else:
            ls_project = client.projects.create(**details)
            print(f"Created project: {ls_project.dict()}")

        # Create or update objects storage's buckets
        bucket_details = _setup_buckets(config, credentials, ls_project, project_draft['storages'])

        # Bind storages to project
        _bind_storages(config, credentials, client, ls_project, bucket_details)


def _setup_buckets(config, credentials, project, storages):
    if not storages:
        print('No storages found')
        return

    token = credentials['yc.service_account']['token']
    sdk = yandexcloud.SDK(token=token)
    folder_id = config['yc.object_storage']['folder']

    bucket_service = sdk.client(BucketServiceStub)
    existed_buckets = [bucket.name for bucket in bucket_service.List(ListBucketsRequest(folder_id=folder_id)).buckets]

    bucket_details = {}
    for storage in storages:
        bucket_name = f"ls-project-{project.id}-{storage['title']}"
        if bucket_name in existed_buckets:
            print(f'Bucket `{bucket_name}` already exists')
        else:
            print(f'Creating bucket `{bucket_name}`')
            bucket_service.Create(
                CreateBucketRequest(
                    folder_id=folder_id,
                    name=bucket_name,
                    **(storage.get('object_storage_params') or {})
                )
            )
        print(f'Configuring bucket `{bucket_name}`')
        bucket_service.Update(
            UpdateBucketRequest(
                name=bucket_name,
                default_storage_class='STANDARD',
                versioning=VERSIONING_DISABLED,
                cors=[CorsRule(
                    allowed_methods=[CorsRule.Method.METHOD_GET],
                    allowed_origins=['*'],
                    allowed_headers=['*'],
                )],
            )
        )
        bucket_details[bucket_name] = storage
    return bucket_details


def _bind_storages(config, credentials, client, ls_project, bucket_details):
    s3endpoint = config['yc.object_storage']['endpoint']
    region_name = config['yc.object_storage']['region_name'],
    aws_access_key_id = credentials['yc.service_account']['aws_access_key_id']
    aws_secret_access_key = credentials['yc.service_account']['aws_secret_access_key']

    for bucket_name, details in bucket_details.items():
        ty = details['type']
        storage_params = details.get('ls_storage_params') or {}
        # for unknown reason, region_name is deserialized as tuple
        storage_params['region_name'] = region_name[0]
        storage_params['s3endpoint'] = s3endpoint
        storage_params['project'] = ls_project.id
        storage_params['bucket'] = bucket_name
        storage_params['aws_access_key_id'] = aws_access_key_id
        storage_params['aws_secret_access_key'] = aws_secret_access_key
        storage_params['title'] = details['title']

        if not ty:
            raise ValueError('Storage type is required')
        elif ty == 'import':
            storage = client.import_storage.s3.create(
                **storage_params
            )
            client.import_storage.s3.sync(storage.id)
        elif ty == 'export':
            storage = client.export_storage.s3.create(
                **storage_params
            )
            client.export_storage.s3.sync(storage.id)
        else:
            raise ValueError(f"Unknown storage type: {ty}, expected 'import' or 'export'")


def _client(config, credentials):
    base_url = config['label_studio.url']
    access_token = credentials['label_studio.access_token']
    return LabelStudio(base_url=base_url, api_key=access_token)


def _find_project_by_title(title, ls):
    projects = ls.projects.list()
    for project in projects:
        if project.title == title:
            return project
    return None


if __name__ == "__main__":
    credentials = _load_yaml('credentials.yaml')
    config = _load_yaml('config.yaml')
    _create_projects(config, credentials)
