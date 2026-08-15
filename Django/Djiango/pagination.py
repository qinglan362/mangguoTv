"""自定义分页：允许客户端通过 ?page_size=N 覆盖每页条数（上限 200）。

DRF 3.17 的 PageNumberPagination.page_size_query_param 硬编码为 None，
不读取全局设置，因此需子类显式开启。
"""
from rest_framework.pagination import PageNumberPagination


class StandardPageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 200
