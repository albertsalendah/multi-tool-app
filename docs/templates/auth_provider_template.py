"""
Authentication Provider Template
"""

class AuthProvider:
    NAME = "example_auth"

    def login(self):
        raise NotImplementedError

    def logout(self):
        pass

    def verify(self, token):
        raise NotImplementedError

    def refresh(self, token):
        raise NotImplementedError
