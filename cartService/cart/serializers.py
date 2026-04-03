from rest_framework import serializers

class AddItemSerializer(serializers.Serializer):
    dish_id = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)


class UpdateQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0)