"""
This script creates manifests in Label Studio, creates buckets in S3 object storage and binds them to manifests.
Project described in `template.yaml` file, credentials described in `credentials.yaml` file.
"""

import os

import yaml
import yandexcloud
from label_studio_sdk.client import LabelStudio
from mergedeep import merge
from yandex.cloud.storage.v1.bucket_pb2 import CorsRule, VERSIONING_DISABLED
from yandex.cloud.storage.v1.bucket_service_pb2 import ListBucketsRequest, CreateBucketRequest, UpdateBucketRequest
from yandex.cloud.storage.v1.bucket_service_pb2_grpc import BucketServiceStub


def _load_yaml(file_path: str):
    """
    Load yaml file by path
    """
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)


def _create_project(config, manifest):
    """
    Create manifests in Label Studio, create buckets in S3 object storage and bind them to manifests

    :param config: configuration file with details of the project
    :param credentials: credentials file with secrets to access Label Studio and S3 object storage
    """
    client = _client(config)
    project_manifest = manifest['project']
    details = project_manifest['details']
    # Create or update project
    title = details.get('title')
    if ai_path := project_manifest.get('instruction_path'):
        with open(ai_path, 'r') as file:
            details['expert_instruction'] = file.read()
    if not title:
        raise ValueError('Project title is required')
    if ls_project := _find_project_by_title(title, client):
        ls_project = client.projects.update(ls_project.id, **details)
        print(f"Updated project: {ls_project.dict()}")
    else:
        ls_project = client.projects.create(**details)
        print(f"Created project: {ls_project.dict()}")

    storages = project_manifest.get('storages') or []
    # Create or update objects storage's buckets
    bucket_details = _setup_buckets(config, ls_project, storages)

    # Bind storages to project
    _bind_storages(config, client, ls_project, bucket_details)


def _setup_buckets(config, project, storages):
    if not config['yc']['object_storage']:
        print('No storages found')
        return

    token = config['yc']['service_account']['token']
    sdk = yandexcloud.SDK(token=token)
    folder_id = config['yc']['object_storage']['folder']

    bucket_service = sdk.client(BucketServiceStub)
    existed_buckets = [bucket.name for bucket in bucket_service.List(ListBucketsRequest(folder_id=folder_id)).buckets]

    bucket_details = {}
    for ty in ['export', 'import']:
        storage = storages.get(ty)
        bucket_name = f"ls-{project.id}-{storage['title']}"
        if bucket_name in existed_buckets:
            print(f'Bucket `{bucket_name}` already exists')
        else:
            print(f'Creating bucket `{bucket_name}`')
            bucket_service.Create(CreateBucketRequest(folder_id=folder_id, name=bucket_name,
                                                      **(storage.get('object_storage_params') or {})))
        print(f'Configuring bucket `{bucket_name}`')
        bucket_service.Update(
            UpdateBucketRequest(name=bucket_name, default_storage_class='STANDARD', versioning=VERSIONING_DISABLED,
                                cors=[CorsRule(allowed_methods=[CorsRule.Method.METHOD_GET], allowed_origins=['*'],
                                               allowed_headers=['*'], )], ))
        bucket_details[bucket_name] = storage
        bucket_details[bucket_name]['type'] = ty
    return bucket_details


def _bind_storages(config, client, ls_project, bucket_details):
    s3endpoint = config['yc']['object_storage']['endpoint']
    region_name = config['yc']['object_storage']['region_name'],
    aws_access_key_id = config['yc']['service_account']['aws_access_key_id']
    aws_secret_access_key = config['yc']['service_account']['aws_secret_access_key']

    for bucket_name, details in bucket_details.items():
        ty = details['type']
        title = details['title']
        storage_params = details.get('ls_storage_params') or {}
        # for unknown reason, region_name is deserialized as tuple
        storage_params['region_name'] = region_name[0]
        storage_params['s3endpoint'] = s3endpoint
        storage_params['project'] = ls_project.id
        storage_params['bucket'] = bucket_name
        storage_params['aws_access_key_id'] = aws_access_key_id
        storage_params['aws_secret_access_key'] = aws_secret_access_key
        storage_params['title'] = title

        if not ty:
            raise ValueError('Storage type is required')
        elif ty == 'import':
            for storage in client.import_storage.s3.list(project=ls_project.id):
                if storage.title == title:
                    print(f"Updating storage `{title}`")
                    client.import_storage.s3.update(storage.id, **storage_params)
                    break
            else:
                print(f"Creating storage `{title}`")
                storage = client.import_storage.s3.create(**storage_params)
                print(f"Syncing storage `{title}`")
            client.import_storage.s3.sync(storage.id)
        elif ty == 'export':
            for storage in client.export_storage.s3.list(project=ls_project.id):
                if storage.title == title:
                    print(f"Updating storage `{title}`")
                    client.export_storage.s3.update(storage.id, **storage_params)
                    break
            else:
                print(f"Creating storage `{title}`")
                storage = client.export_storage.s3.create(**storage_params)
                print(f"Syncing storage `{title}`")
            client.export_storage.s3.sync(storage.id)
        else:
            raise ValueError(f"Unknown storage type: {ty}, expected 'import' or 'export'")


def _client(config):
    base_url = config['label_studio']['url']
    access_token = config['label_studio']['access_token']
    return LabelStudio(base_url=base_url, api_key=access_token)


def _find_project_by_title(title, ls):
    projects = ls.projects.list()
    for project in projects:
        if project.title == title:
            return project
    return None


def _create_projects():
    config = _load_yaml('config.yaml')
    template = _load_yaml('template.yaml')
    for _, _, files in os.walk('manifests'):
        for f in files:
            manifest = _load_yaml(os.path.join('manifests', f))
            merged = merge(template, manifest)
            _create_project(config, merged)


if __name__ == "__main__":
    _create_projects()
