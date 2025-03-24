# =============================================================================
# Global Counters and Decorator for Function Calls
# =============================================================================

FUNC_CALLS = {}

def count_calls(func):
    def wrapper(*args, **kwargs):
        FUNC_CALLS[func.__name__] = FUNC_CALLS.get(func.__name__, 0) + 1
        return func(*args, **kwargs)
    return wrapper
