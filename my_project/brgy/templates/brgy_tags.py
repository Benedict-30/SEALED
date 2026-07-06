from django import template

register = template.Library()


@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter(name='add')
def add_filter(value, arg):
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def truncate_chars(value, max_length):
    if len(value) > max_length:
        return value[:max_length] + '...'
    return value


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)