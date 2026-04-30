from app import cache


def clear_dashboard_cache(tenant_id, floor):
    from .pantry.routes import _get_dashboard_stats

    cache.delete_memoized(_get_dashboard_stats, tenant_id, floor)