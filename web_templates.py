#
# web templates.
#
template_cache = {}


def get_page_template(template_name):
    template = template_cache.get(template_name)
    if template is None:
        with open('templates/' + template_name + '.html', 'r') as templateFile:
            template = templateFile.read()
            template_cache[template_name] = template
    return template


def apply_page_template(template, **kwargs):
    for k, v in kwargs.items():
        target = '{{ ' + k + ' }}'
        if target in template:
            template = template.replace(target, str(v))
        else:
            print(f'warning: cannot find target {k}')
    return template

