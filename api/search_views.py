# backend/api/search_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from core_engine.symbol_resolver import search_companies


class SearchSuggestionsAPI(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        q = request.GET.get("q", "").strip()

        if not q:
            return Response([], status=status.HTTP_200_OK)

        results = search_companies(q)

        return Response(results, status=status.HTTP_200_OK)
