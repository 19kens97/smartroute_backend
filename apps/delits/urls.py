from rest_framework.routers import DefaultRouter
from .views import DelitCaseViewSet, DelitTypeViewSet

router=DefaultRouter()
router.register('types',DelitTypeViewSet,basename='delit-type')
router.register('',DelitCaseViewSet,basename='delit')
urlpatterns=router.urls
