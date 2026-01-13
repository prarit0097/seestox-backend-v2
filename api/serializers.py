from rest_framework import serializers


class SubscriptionPlanSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    price_inr = serializers.IntegerField()
    interval = serializers.CharField()
    features = serializers.ListField(child=serializers.CharField())


class SubscriptionStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    is_active = serializers.BooleanField()
    access_level = serializers.CharField()
    plan = serializers.DictField(allow_null=True)
    trial = serializers.DictField()
    current_period = serializers.DictField()
    paywall = serializers.DictField()
