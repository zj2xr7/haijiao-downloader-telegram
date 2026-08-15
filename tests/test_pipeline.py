"""
Tests for PipelineManager.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from src.core.pipeline import PipelineManager
from src.models import PostDetail, TaskStage, AuthorPostItem


@pytest.mark.asyncio
async def test_pipeline_single_post_execution(tmp_path):
    mock_crawler = MagicMock()
    mock_crawler.fetch_post_detail = AsyncMock(return_value=PostDetail(
        post_id="111",
        title="Sample Post",
        author_id="a1",
        author_name="Author1",
        source_url="http://example.com/111"
    ))
    
    mock_decryptor = MagicMock()
    mock_decryptor.download_and_decrypt_image = AsyncMock(return_value=True)
    mock_decryptor.download_and_decrypt_video_m3u8 = AsyncMock(return_value=True)
    
    post_dir = tmp_path / "post_dir"
    post_dir.mkdir()
    
    mock_renderer = MagicMock()
    mock_renderer.prepare_post_directory = MagicMock(return_value=post_dir)
    mock_renderer.get_author_folder_name = MagicMock(return_value="Author1_a1")
    mock_renderer.get_post_folder_name = MagicMock(return_value="[111] Sample Post")
    mock_renderer.save_markdown_file = MagicMock(return_value=post_dir / "post.md")
    
    mock_disk_guard = MagicMock()
    mock_disk_guard.get_free_space_gb = MagicMock(return_value=10.0)
    mock_disk_guard.acquire_download_slot = AsyncMock()
    mock_disk_guard.release_download_slot = MagicMock()
    mock_disk_guard.notify_disk_freed = MagicMock()
    
    mock_uploader = MagicMock()
    mock_uploader.upload_and_cleanup = AsyncMock(return_value=(True, ""))
    mock_uploader.get_openlist_url = MagicMock(return_value="https://pan.example.com/view/111")
    
    pipeline = PipelineManager(
        crawler=mock_crawler,
        decryptor=mock_decryptor,
        renderer=mock_renderer,
        disk_guard=mock_disk_guard,
        uploader=mock_uploader
    )
    
    result = await pipeline.process_single_post("111")
    assert result.stage == TaskStage.COMPLETED
    assert result.post_id == "111"
    assert result.openlist_url == "https://pan.example.com/view/111"
    
    mock_disk_guard.acquire_download_slot.assert_called_once()
    mock_disk_guard.release_download_slot.assert_called_once()
    mock_uploader.upload_and_cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_author_pages_batch():
    mock_crawler = MagicMock()
    mock_crawler.fetch_author_posts = AsyncMock(return_value=[
        AuthorPostItem(post_id="101", title="Post 101"),
        AuthorPostItem(post_id="102", title="Post 102")
    ])
    mock_crawler.fetch_post_detail = AsyncMock(side_effect=lambda pid: PostDetail(
        post_id=pid,
        title=f"Title {pid}",
        author_id="a1",
        author_name="Author1",
        source_url=f"http://example.com/{pid}"
    ))
    
    pipeline = PipelineManager(
        crawler=mock_crawler,
        decryptor=MagicMock(),
        renderer=MagicMock(),
        disk_guard=MagicMock(),
        uploader=MagicMock()
    )
    
    pipeline.process_single_post = AsyncMock(side_effect=lambda pid, progress_callback=None: MagicMock(
        post_id=pid,
        stage=TaskStage.COMPLETED
    ))
    
    results = []
    async for res in pipeline.process_author_pages("a1", pages=[1]):
        results.append(res)
        
    assert len(results) == 2
    assert results[0].post_id == "101"
    assert results[1].post_id == "102"
