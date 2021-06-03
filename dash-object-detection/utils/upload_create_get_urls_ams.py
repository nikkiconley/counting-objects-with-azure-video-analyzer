"""
Based on:  https://stackoverflow.com/questions/58815813/uploading-a-video-to-azure-media-services-with-python-sdks
"""
from azure.mgmt.media.models import Asset, Transform, Job, 
    BuiltInStandardEncoderPreset, TransformOutput, \
    JobInputAsset, JobOutputAsset, AssetContainerSas, AssetContainerPermission

import adal
from msrestazure.azure_active_directory import AdalAuthentication
from msrestazure.azure_cloud import AZURE_PUBLIC_CLOUD
from azure.mgmt.media import AzureMediaServices
from azure.storage.blob import BlobServiceClient, ContainerClient
import datetime as dt
import time
from collections import namedtuple


LOGIN_ENDPOINT = AZURE_PUBLIC_CLOUD.endpoints.active_directory
RESOURCE = AZURE_PUBLIC_CLOUD.endpoints.active_directory_resource_id

azure_tuple = namedtuple('settings', 'AZURE_MEDIA_TENANT_ID AZURE_MEDIA_CLIENT_ID AZURE_MEDIA_SECRET AZURE_SUBSCRIPTION_ID')

def get_ams_client(settings: AzureSettings) -> AzureMediaServices:
    context = adal.AuthenticationContext(LOGIN_ENDPOINT + '/' + 
        settings.AZURE_MEDIA_TENANT_ID)
    credentials = AdalAuthentication(
        context.acquire_token_with_client_credentials,
        RESOURCE,
        settings.AZURE_MEDIA_CLIENT_ID,
        settings.AZURE_MEDIA_SECRET
    )
    return AzureMediaServices(credentials, settings.AZURE_SUBSCRIPTION_ID)

input_asset = create_or_update_asset(
    input_asset_name, "My Input Asset", client, azure_settings)
input_asset = create_or_update_asset(
    output_asset_name, "My Output Asset", client, azure_settings)

def get_container_name(client: AzureMediaServices, asset_name: str, settings: AzureSettings):
    expiry_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)
    container_list: AssetContainerSas = client.assets.list_container_sas(
        resource_group_name=settings.AZURE_MEDIA_RESOURCE_GROUP_NAME,
        account_name=settings.AZURE_MEDIA_ACCOUNT_NAME,
        asset_name=asset_name,
        permissions = AssetContainerPermission.read_write,
        expiry_time=expiry_time
    )
    sas_uri: str = container_list.asset_container_sas_urls[0]
    container_client: ContainerClient = ContainerClient.from_container_url(sas_uri)
    return container_client.container_name

def upload_file_to_asset_container(
    container: str, local_file, uploaded_file_name, settings: AzureSettings):
    blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_MEDIA_STORAGE_CONNECTION_STRING))
    blob_client = blob_service_client.get_blob_client(container=container, blob=uploaded_file_name)

    with open(local_file, 'rb') as data:
            blob_client.upload_blob(data)

def get_or_create_transform(
    client: AzureMediaServices,
    transform_name: str,
    settings: AzureSettings):
    transform_output = TransformOutput(preset=BuiltInStandardEncoderPreset(preset_name="AdaptiveStreaming"))
    transform: Transform = client.transforms.create_or_update(
        resource_group_name=settings.AZURE_MEDIA_RESOURCE_GROUP_NAME,
        account_name=settings.AZURE_MEDIA_ACCOUNT_NAME,
        transform_name=transform_name,
        outputs=[transform_output]
    )
    return transform

def submit_job(
    client: AzureMediaServices,
    settings: AzureSettings,
    input_asset: Asset,
    output_asset: Asset,
    transform_name: str,
    correlation_data: dict) -> Job:

    job_input = JobInputAsset(asset_name=input_asset.name)
    job_outputs = [JobOutputAsset(asset_name=output_asset.name)]
    job: Job = client.jobs.create(
        resource_group_name=settings.AZURE_MEDIA_RESOURCE_GROUP_NAME,
        account_name=settings.AZURE_MEDIA_ACCOUNT_NAME,
        job_name=f"test_job_{UNIQUENESS}",
        transform_name=transform_name,
        parameters=Job(input=job_input,
            outputs=job_outputs,
            correlation_data=correlation_data)
    )
    return job

# side-effect warning: this starts the streaming endpoint $$$
def get_urls(client: AzureMediaServices, output_asset_name: str,
    locator_name: str):

    try:
        locator: StreamingLocator = client.streaming_locators.create(
            resource_group_name=settings.AZURE_MEDIA_RESOURCE_GROUP_NAME,
            account_name=settings.AZURE_MEDIA_ACCOUNT_NAME,
            streaming_locator_name=locator_name,
            parameters=StreamingLocator(
                asset_name=output_asset_name,
                streaming_policy_name="Predefined_ClearStreamingOnly"
            )
        )
    except Exception as ex:
        print("ignoring existing")

    streaming_endpoint: StreamingEndpoint = client.streaming_endpoints.get(
        resource_group_name=settings.AZURE_MEDIA_RESOURCE_GROUP_NAME,
        account_name=settings.AZURE_MEDIA_ACCOUNT_NAME,
        streaming_endpoint_name="default")

    if streaming_endpoint:
        if streaming_endpoint.resource_state != "Running":
            client.streaming_endpoints.start(
                resource_group_name=settings.AZURE_MEDIA_RESOURCE_GROUP_NAME,
                account_name=settings.AZURE_MEDIA_ACCOUNT_NAME,
                streaming_endpoint_name="default"
            )

    paths = client.streaming_locators.list_paths(
        resource_group_name=settings.AZURE_MEDIA_RESOURCE_GROUP_NAME,
        account_name=settings.AZURE_MEDIA_ACCOUNT_NAME,
        streaming_locator_name=locator_name
    )

    return [f"https://{streaming_endpoint.host_name}{path.paths[0]}" for path in paths.streaming_paths]
