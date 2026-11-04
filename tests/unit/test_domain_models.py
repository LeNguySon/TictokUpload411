"""
Unit tests for Domain Models: Profile, Project, Proxy, VideoDraft, UploadJob.
Strict TDD - Phase 2 (RED)
"""

import pytest
from src.domain.models.profile import ProfileDomainModel, ProfileStatus
from src.domain.models.project import ProjectDomainModel
from src.domain.models.proxy import ProxyDomainModel, ProxyStatus, ProxyType
from src.domain.models.upload_job import UploadExecutionMode, UploadJobDomainModel, UploadJobStatus
from src.domain.models.video import PrivacyLevel, VideoDraftDomainModel, VideoStatus


def test_profile_domain_model_creation_and_status():
    profile = ProfileDomainModel(
        id=1,
        name="TikTok_US_01",
        project_id=10,
        proxy_id=5,
        status=ProfileStatus.LIVE,
        username_on_tiktok="creator_mike",
        views_30d=150000,
        t_follows=5200,
        t_views=1200000,
        t_video=45,
        email="mike@domain.com",
        cookie="msToken=xyz; sessionid=abc",
        balance=1250.50,
        rpm=0.45,
        qg="US",
        kyc="Yes",
        privacy="PUBLIC",
    )
    assert profile.is_ready_to_upload() is True
    assert profile.is_alive() is True

    # Test invalid transition
    profile.mark_checkpoint()
    assert profile.status == ProfileStatus.CHECKPOINT
    assert profile.is_ready_to_upload() is False

    profile.mark_die()
    assert profile.status == ProfileStatus.DIE
    assert profile.is_alive() is False


def test_project_domain_model_validation():
    # Valid project
    proj = ProjectDomainModel(
        id=1,
        name="Campaign Alpha",
        description="US TikTok Beta Accounts",
        is_default=False,
    )
    assert proj.name == "Campaign Alpha"

    # Name cannot be blank
    with pytest.raises(ValueError, match="Project name cannot be empty"):
        ProjectDomainModel(id=2, name="   ")


def test_proxy_domain_model_conversion_and_export():
    proxy = ProxyDomainModel(
        id=1,
        scheme=ProxyType.HTTP,
        host="192.168.1.50",
        port=8080,
        username="usr",
        password="pwd",
        change_ip_url="https://proxy-provider.com/rotate?key=123",
        status=ProxyStatus.ALIVE,
        latency_ms=120.5,
    )
    # Check string formatting for various tools
    assert proxy.to_export_format() == "192.168.1.50:8080:usr:pwd"
    assert proxy.to_uri() == "http://usr:pwd@192.168.1.50:8080"
    assert proxy.supports_rotation is True

    # Convert to sammonny ProxyItem
    sdk_item = proxy.to_sammonny_item()
    assert sdk_item.host == "192.168.1.50"
    assert sdk_item.port == 8080
    assert sdk_item.username == "usr"
    assert sdk_item.password == "pwd"
    assert sdk_item.change_ip_url == "https://proxy-provider.com/rotate?key=123"


def test_video_draft_domain_model():
    video = VideoDraftDomainModel(
        id=10,
        file_path="C:/videos/dance_01.mp4",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        title="Epic Dance Compilation #fyp",
        duration_seconds=45.2,
        privacy_level=PrivacyLevel.PUBLIC_TO_EVERYONE,
        status=VideoStatus.PENDING,
    )
    assert video.title == "Epic Dance Compilation #fyp"
    assert video.is_scheduled is False
    assert video.can_be_assigned() is True

    # Mark assigned
    video.assign_to_profile(profile_id=100)
    assert video.upload_to_profile_id == 100
    assert video.status == VideoStatus.ASSIGNED
    assert video.can_be_assigned() is False


def test_upload_job_domain_model_lifecycle():
    job = UploadJobDomainModel(
        job_id="job_998877",
        video_id=10,
        profile_id=100,
        mode=UploadExecutionMode.OFFICIAL_DIRECT_POST,
    )
    assert job.status == UploadJobStatus.QUEUED
    assert job.retry_count == 0

    # Start upload
    job.mark_in_progress()
    assert job.status == UploadJobStatus.IN_PROGRESS

    # Record retry
    job.record_failure(error_msg="Rate limit HTTP 429", retryable=True)
    assert job.status == UploadJobStatus.RETRYING
    assert job.retry_count == 1
    assert "429" in job.last_error

    # Final success
    job.mark_completed(publish_id="v_pub_tiktok_abc123")
    assert job.status == UploadJobStatus.COMPLETED
    assert job.publish_id == "v_pub_tiktok_abc123"
