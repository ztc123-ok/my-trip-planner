"""景点图片多源获取与降级服务（高德 POI 官方 photos 优先 -> DDGS Bing 搜索回退 -> 兜底空值）。"""

import logging
from threading import Lock
from typing import Optional

from .amap_service import get_amap_service
from .ddgs_photo_service import get_ddgs_photo_service

logger = logging.getLogger(__name__)


def extract_parent_attraction(name: str) -> Optional[str]:
    """提取复合子景点的母体景区名称，用于递进式回退检索。
    例如：
    '玉渊潭公园-留春园' -> '玉渊潭公园'
    '故宫博物院-堆秀山' -> '故宫博物院'
    '西海湿地公园-景观平台' -> '西海湿地公园'
    '北海公园(荷花湖)' -> '北海公园'
    '太庙-神柏' -> '太庙'
    """
    if not name:
        return None
    clean = name.strip()
    # 常用层级分隔符
    for sep in ("-", "—", "_", "·"):
        if sep in clean:
            parent = clean.split(sep, 1)[0].strip()
            if len(parent) >= 2 and parent != clean:
                return parent
    # 括号包含的子景点/注释
    for start_bracket, end_bracket in (("（", "）"), ("(", ")")):
        if start_bracket in clean and clean.endswith(end_bracket):
            parent = clean.split(start_bracket, 1)[0].strip()
            if len(parent) >= 2 and parent != clean:
                return parent
    return None


class UnifiedPhotoService:
    """多源图片检索服务。"""

    def __init__(self, amap_service=None, ddgs_service=None):
        self._amap_service = amap_service
        self._ddgs_service = ddgs_service
        self._cache: dict[str, Optional[str]] = {}
        self._lock = Lock()

    @property
    def amap_service(self):
        if self._amap_service is None:
            self._amap_service = get_amap_service()
        return self._amap_service

    @property
    def ddgs_service(self):
        if self._ddgs_service is None:
            self._ddgs_service = get_ddgs_photo_service()
        return self._ddgs_service

    def get_photo_url(self, name: str, city: str = "") -> Optional[str]:
        """按优先级与递进策略多源获取景点图片：
        1. 原名首选源：高德 POI 官方实景照片 (photos 字段)
        2. 原名备选源：DDGS Bing 图片搜索引擎
        3. 递进回退源：若为复合子景点（含 -、·、括号等），截断提取母体主景区，递进检索高德/Bing
        4. 止损兜底：避免语义漂移与张冠李戴，返回 None（由前端默认渐变占位图兜底）
        """
        if not name or not name.strip():
            return None

        clean_name = name.strip()
        clean_city = city.strip() if city else ""
        cache_key = f"{clean_city}::{clean_name}"

        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        # 1. 原名首选源：高德 POI 官方 photos 字段
        try:
            amap_photo = self.amap_service.get_poi_photo(name=clean_name, city=clean_city)
            if amap_photo:
                logger.info("景点图片命中 [高德POI]: %s (城市: %s) -> %s", clean_name, clean_city, amap_photo)
                with self._lock:
                    self._cache[cache_key] = amap_photo
                return amap_photo
        except Exception as exc:
            logger.warning("高德POI图片获取异常 (%s): %s", clean_name, exc)

        # 2. 原名备选源：DDGS Bing 图片搜索引擎
        try:
            logger.info("高德未提供照片或不可用，回退至 Bing 图片搜索: %s (城市: %s)", clean_name, clean_city)
            bing_photo = self.ddgs_service.get_photo_url(name=clean_name, city=clean_city)
            if bing_photo:
                logger.info("景点图片命中 [Bing搜索]: %s (城市: %s) -> %s", clean_name, clean_city, bing_photo)
                with self._lock:
                    self._cache[cache_key] = bing_photo
                return bing_photo
        except Exception as exc:
            logger.warning("Bing图片搜索异常 (%s): %s", clean_name, exc)

        # 3. 递进回退源：尝试截断母体大景区（针对子景点、园中园）
        parent_name = extract_parent_attraction(clean_name)
        if parent_name:
            logger.info("原名未命中，触发母体景区递进重试: %s -> 母体 %s", clean_name, parent_name)
            # 3.1 尝试母体的高德 POI 官方照片
            try:
                parent_amap_photo = self.amap_service.get_poi_photo(name=parent_name, city=clean_city)
                if parent_amap_photo:
                    logger.info("景点图片命中 [母体高德POI]: %s (母体: %s) -> %s", clean_name, parent_name, parent_amap_photo)
                    with self._lock:
                        self._cache[cache_key] = parent_amap_photo
                    return parent_amap_photo
            except Exception as exc:
                logger.warning("母体高德POI图片获取异常 (%s -> %s): %s", clean_name, parent_name, exc)

            # 3.2 尝试母体的 Bing 图片搜索
            try:
                parent_bing_photo = self.ddgs_service.get_photo_url(name=parent_name, city=clean_city)
                if parent_bing_photo:
                    logger.info("景点图片命中 [母体Bing搜索]: %s (母体: %s) -> %s", clean_name, parent_name, parent_bing_photo)
                    with self._lock:
                        self._cache[cache_key] = parent_bing_photo
                    return parent_bing_photo
            except Exception as exc:
                logger.warning("母体Bing图片搜索异常 (%s -> %s): %s", clean_name, parent_name, exc)

        # 4. 止损兜底：返回 None，由前端优雅占位图展示
        logger.info("所有递进检索均未获取到图片，止损降级由前端占位图兜底: %s", clean_name)
        with self._lock:
            self._cache[cache_key] = None
        return None


_photo_service: Optional[UnifiedPhotoService] = None
_service_lock = Lock()


def get_photo_service() -> UnifiedPhotoService:
    global _photo_service
    with _service_lock:
        if _photo_service is None:
            _photo_service = UnifiedPhotoService()
        return _photo_service
