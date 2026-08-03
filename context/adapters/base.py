"""Base adapter interface for message conversion."""
from abc import ABC, abstractmethod
from typing import Any, List

from db.models import StoredMessage


class MessageAdapter(ABC):
    """Abstract interface for converting between framework-specific messages and storage.
    
    Different adapters implement this interface for different frameworks:
    - LangChainMessageAdapter: For LangChain messages
    - OpenAIMessageAdapter: For OpenAI message format
    - CustomMessageAdapter: For custom message types
    """
    
    @abstractmethod
    def to_framework(self, stored: StoredMessage) -> Any:
        """Convert a StoredMessage to framework-specific message.
        
        Args:
            stored: StoredMessage from database
            
        Returns:
            Framework-specific message object (e.g., LangChain BaseMessage)
        """
        pass
    
    @abstractmethod
    def from_framework(self, message: Any) -> StoredMessage:
        """Convert framework-specific message to StoredMessage.
        
        Args:
            message: Framework-specific message object
            
        Returns:
            StoredMessage for database storage
        """
        pass
    
    @abstractmethod
    def create_system_message(self, content: str) -> Any:
        """Create a system message in framework-specific format.
        
        Args:
            content: System message content
            
        Returns:
            Framework-specific system message
        """
        pass
    
    @abstractmethod
    def create_user_message(self, content: str) -> Any:
        """Create a user message in framework-specific format.
        
        Args:
            content: User message content
            
        Returns:
            Framework-specific user message
        """
        pass
    
    @abstractmethod
    def sanitize_messages(self, messages: List[Any]) -> List[Any]:
        """Sanitize a list of messages to ensure validity.
        
        For example, ensure every AIMessage with tool_calls has
        corresponding ToolMessage.
        
        Args:
            messages: List of framework-specific messages
            
        Returns:
            Sanitized list of messages
        """
        pass
    
    @abstractmethod
    def get_message_type(self, message: Any) -> str:
        """Get the type of a framework-specific message.
        
        Args:
            message: Framework-specific message
            
        Returns:
            Message type string (e.g., 'user', 'assistant', 'tool', 'system')
        """
        pass
