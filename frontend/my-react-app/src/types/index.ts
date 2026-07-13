export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface ConfirmationInfo {
  type: "confirmation_required";
  session_id: string;
  thread_id: string;
}

export interface ConfirmationState {
  thread_id: string;
  session_id: string;
  content: string;
  afterMessageId: string;
}

export interface SSEData {
  content: string;
  confirmation: ConfirmationInfo | null;
  session_id: string;
}

export interface ChatRequest {
  text: string;
  session_id?: string;
  permissions?: string[];
}

export interface ConfirmRequest {
  thread_id: string;
  session_id: string;
}

export interface ConversationItem {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationsResponse {
  session_id: string;
  conversations: ConversationItem[];
}
