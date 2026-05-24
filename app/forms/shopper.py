class ShopperSearchForm:
    def __init__(self, query="", property_id=None):
        self.query = (query or "").strip()
        self.property_id = property_id

    @classmethod
    def from_request_args(cls, request_args):
        return cls(
            query=request_args.get("query", ""),
            property_id=request_args.get("property_id", type=int),
        )
