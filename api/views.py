from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.route import PlanError, plan_route


class RouteRequestSerializer(serializers.Serializer):
    """Both fields are required strings: a place name or 'lat,lng'."""

    start = serializers.CharField()
    finish = serializers.CharField()


class RouteView(APIView):
    """GET shows the form. POST plans the route."""

    def get(self, request):
        return Response({"detail": "POST JSON {\"start\": \"lat,lng\", \"finish\": \"lat,lng\"}."})

    def post(self, request):
        ser = RouteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            return Response(plan_route(ser.validated_data["start"], ser.validated_data["finish"]))
        except PlanError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
