"""
Storage Provider Template
"""

class StorageProvider:
    NAME = "example_storage"

    def connect(self):
        pass

    def upload(self, output_bundle):
        raise NotImplementedError

    def delete(self, resource_id):
        raise NotImplementedError

    def disconnect(self):
        pass
