from app.services.adapters.base import SourceAdapter


def get_source_adapter(source: str) -> SourceAdapter:
    if source != "douban":
        raise ValueError(f"Unsupported source: {source}")
    from app.services.adapters.douban import DoubanAdapter

    return DoubanAdapter()
