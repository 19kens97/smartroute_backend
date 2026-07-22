from rest_framework.pagination import PageNumberPagination


class DelitPagination(PageNumberPagination):
    page_size = 40
    page_size_query_param = "page_size"
    max_page_size = 100
