"""
文件服务 API 路由
"""

import aiofiles.os
from urllib.parse import unquote
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
import httpx

from app.core.logger import logger
from app.core.storage import DATA_DIR

router = APIRouter(tags=["Files"])

# 缓存根目录
BASE_DIR = DATA_DIR / "tmp"
IMAGE_DIR = BASE_DIR / "image"
VIDEO_DIR = BASE_DIR / "video"


def _normalize_cached_filename(filename: str) -> str:
    """
    规范化客户端传入文件名，兼容尾部误带反斜杠等情况。
    """
    value = (filename or "").strip()
    # 尝试解码一次，兼容 %5C 这类编码
    try:
        value = unquote(value)
    except Exception:
        pass
    value = value.strip().strip('"').strip("'").rstrip("\\/")
    # 将路径分隔符统一扁平化到缓存命名规则
    value = value.replace("\\", "-").replace("/", "-")
    return value


@router.get("/image/{filename:path}")
async def get_image(filename: str):
    """
    获取图片文件
    """
    filename = _normalize_cached_filename(filename)

    file_path = IMAGE_DIR / filename

    if await aiofiles.os.path.exists(file_path):
        if await aiofiles.os.path.isfile(file_path):
            content_type = "image/jpeg"
            if file_path.suffix.lower() == ".png":
                content_type = "image/png"
            elif file_path.suffix.lower() == ".webp":
                content_type = "image/webp"

            # 增加缓存头，支持高并发场景下的浏览器/CDN缓存
            return FileResponse(
                file_path,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )

    logger.warning(f"Image not found: {filename}")
    raise HTTPException(status_code=404, detail="Image not found")


@router.get("/video/{filename:path}")
async def get_video(filename: str):
    """
    获取视频文件
    """
    filename = _normalize_cached_filename(filename)

    file_path = VIDEO_DIR / filename

    if await aiofiles.os.path.exists(file_path):
        if await aiofiles.os.path.isfile(file_path):
            return FileResponse(
                file_path,
                media_type="video/mp4",
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )

    logger.warning(f"Video not found: {filename}")
    raise HTTPException(status_code=404, detail="Video not found")


@router.get("/proxy")
async def proxy_file(url: str, request: Request):
    """
    代理文件，伪造 User-Agent 和 Referer 绕过防盗链
    """
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    async with httpx.AsyncClient() as client:
        try:
            referer = request.headers.get("referer") or str(request.base_url)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": referer,
            }

            req = client.build_request("GET", url, headers=headers)
            r = await client.send(req, stream=True)
            r.raise_for_status()

            response_headers = {
                key: value
                for key, value in r.headers.items()
                if key.lower() not in ["content-length", "transfer-encoding", "connection", "content-encoding"]
            }

            return StreamingResponse(
                r.aiter_bytes(),
                headers=response_headers,
                status_code=r.status_code,
                media_type=r.headers.get("content-type"),
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Proxy request failed for url {url} with status {e.response.status_code}: {e}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch URL: Server returned status {e.response.status_code}")
        except Exception as e:
            logger.error(f"Proxy request failed for url {url}: {e}")
            raise HTTPException(status_code=500, detail=f"An error occurred while fetching the URL: {e}")
