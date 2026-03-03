"""
Firebase configuration and initialization.
Centralized Firebase setup with proper error handling and connection management.
"""
import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
from firebase_admin.exceptions import FirebaseError

logger = logging.getLogger(__name__)


@dataclass
class FirebaseConfig:
    """Firebase configuration dataclass for type safety."""
    project_id: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    auth_uri: str = "https://accounts.google.com/o/oauth2/auth"
    token_uri: str = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url: str = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url: str = "https://www.googleapis.com/robot/v1/metadata/x509/"
    
    @classmethod
    def from_env(cls) -> Optional['FirebaseConfig']:
        """Load Firebase configuration from environment variables."""
        try:
            project_id = os.getenv('FIREBASE_PROJECT_ID')
            private_key_id = os.getenv('FIREBASE_PRIVATE_KEY_ID')
            private_key = os.getenv('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n')
            client_email = os.getenv('FIREBASE_CLIENT_EMAIL')
            client_id = os.getenv('FIREBASE_CLIENT_ID')
            
            if not all([project_id, private_key_id, private_key, client_email, client_id]):
                logger.warning("Missing Firebase environment variables")
                return None
                
            return cls(
                project_id=project_id,
                private_key_id=private_key_id,
                private_key=private_key,
                client_email=client_email,
                client_id=client_id
            )
        except Exception as e:
            logger.error(f"Error loading Firebase config from env: {e}")
            return None


class FirebaseManager:
    """Singleton Firebase manager with connection pooling and error recovery."""
    
    _instance = None
    _app = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = False
            self.config: Optional[FirebaseConfig] = None
    
    def initialize(self, config: Optional[FirebaseConfig] = None) -> bool:
        """
        Initialize Firebase connection.
        
        Args:
            config: FirebaseConfig instance or None to load from env
            
        Returns:
            bool: True if initialization successful
        """
        if self.initialized:
            logger.info("Firebase already initialized")
            return True
            
        try:
            # Load config if not provided
            if config is None:
                self.config = FirebaseConfig.from_env()
                if self.config is None:
                    logger.error("Could not load Firebase configuration")
                    return False
            else:
                self.config = config
            
            # Create credential dictionary
            cred_dict = {
                "type": "service_account",
                "project_id": self.config.project_id,
                "private_key_id": self.config.private_key_id,
                "private_key": self.config.private_key,
                "client_email": self.config.client_email,
                "client_id": self.config.client_id,
                "auth_uri": self.config.auth_uri,
                "token_uri": self.config.token_uri,
                "auth_provider_x509_cert_url": self.config.auth_provider_x509_cert_url,
                "client_x509_cert_url": f"{self.config.client_x509_cert_url}{self.config.client_email}"
            }
            
            # Initialize Firebase app
            credential = credentials.Certificate(cred_dict)
            
            # Check if app already exists
            if not firebase_admin._apps:
                self._app = initialize_app(credential, {
                    'projectId': self.config.project_id,
                })
            else:
                self._app = firebase_admin.get_app()
            
            # Initialize Firestore
            self._db = firestore.client(app=self._app)
            
            # Test connection
            test_ref = self._db.collection('connection_test').document('test')
            test_ref.set({'timestamp': firestore.SERVER_TIMESTAMP}, merge=True)
            test_ref.delete()
            
            self.initialized = True
            logger.info("Firebase initialized successfully")
            return True
            
        except FirebaseError as e:
            logger.error(f"Firebase initialization error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Firebase initialization: {e}")
            return False
    
    @property
    def db(self) -> firestore.Client:
        """Get Firestore client instance."""
        if not self.initialized or self._db is None:
            raise RuntimeError("Firebase not initialized. Call initialize() first.")
        return self._db
    
    @property
    def app(self):
        """Get Firebase app instance."""
        if not self.initialized or self._app is None:
            raise RuntimeError("Firebase not initialized. Call initialize() first.")
        return self._app
    
    def close(self):
        """Clean up Firebase resources."""
        if self._app:
            try:
                firebase_admin.delete_app(self._app)
                self._app = None
                self._db = None
                self.initialized = False
                logger.info("Firebase connection closed")
            except Exception as e:
                logger.error(f"Error closing Firebase connection: {e}")


# Global Firebase manager instance
firebase_manager = FirebaseManager()


def get_firestore() -> firestore.Client:
    """Helper function to get Firestore client with lazy initialization."""
    if not firebase_manager.initialized:
        if not firebase_manager.initialize():
            raise RuntimeError("