import { create } from "zustand";
import type { Message, ConfirmationState } from "@/types";
import { streamChatSSE, streamConfirmSSE, fetchConversations } from "@/api/chat";

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

interface ChatStore {
  messages: Message[];
  sessionId: string;
  isLoading: boolean;
  confirmation: ConfirmationState | null;

  loadHistory: (sessionId: string) => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  triggerWorkflow: () => Promise<void>;
  confirmAction: (threadId: string, sessionId: string) => Promise<void>;
  rejectAction: (threadId: string, sessionId: string) => Promise<void>;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  sessionId: "",
  isLoading: false,
  confirmation: null,

  loadHistory: async (sessionId: string) => {
    try {
      const data = await fetchConversations(sessionId);
      const historyMessages: Message[] = data.conversations.map((item) => ({
        id: generateId(),
        role: item.role,
        content: item.content,
        timestamp: new Date(item.created_at).getTime(),
      }));
      set({ messages: historyMessages, sessionId: data.session_id });
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  },

  sendMessage: async (text: string) => {
    const { sessionId } = get();

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: text,
      timestamp: Date.now(),
    };

    const assistantMessage: Message = {
      id: generateId(),
      role: "assistant",
      content: "",
      timestamp: Date.now(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage, assistantMessage],
      isLoading: true,
    }));

    try {
      const stream = streamChatSSE({
        text,
        session_id: sessionId || undefined,
      });

      for await (const event of stream) {
        // Save session_id on first receive
        if (event.session_id && !get().sessionId) {
          set({ sessionId: event.session_id });
        }
        // Also update sessionId if it changes
        if (event.session_id) {
          set({ sessionId: event.session_id });
        }

        // Append content to the last assistant message
        if (event.content) {
          set((state) => {
            const messages = [...state.messages];
            const lastIdx = messages.length - 1;
            if (lastIdx >= 0 && messages[lastIdx].role === "assistant") {
              messages[lastIdx] = {
                ...messages[lastIdx],
                // Add newline after each SSE content chunk
                content: messages[lastIdx].content + event.content + "\n",
              };
            }
            return { messages };
          });
        }

        // Handle confirmation request
        if (event.confirmation) {
          const lastAssistantId = get().messages.filter(m => m.role === "assistant").slice(-1)[0]?.id || "";
          set({
            confirmation: {
              thread_id: event.confirmation.thread_id,
              session_id: event.confirmation.session_id,
              content: event.content || "",
              afterMessageId: lastAssistantId,
            },
          });
        }
      }
    } catch (err) {
      console.error("SSE stream error:", err);
      // Update the assistant message with error
      set((state) => {
        const messages = [...state.messages];
        const lastIdx = messages.length - 1;
        if (lastIdx >= 0 && messages[lastIdx].role === "assistant") {
          messages[lastIdx] = {
            ...messages[lastIdx],
            content: messages[lastIdx].content || "Connection error, please try again.",
          };
        }
        return { messages };
      });
    } finally {
      set({ isLoading: false });
    }
  },

  triggerWorkflow: async () => {
    const { sessionId } = get();

    const assistantMessage: Message = {
      id: generateId(),
      role: "assistant",
      content: "",
      timestamp: Date.now(),
    };

    set((state) => ({
      messages: [...state.messages, assistantMessage],
      isLoading: true,
    }));

    try {
      const stream = streamChatSSE({
        text: "",
        session_id: sessionId || undefined,
      });

      for await (const event of stream) {
        if (event.session_id) {
          set({ sessionId: event.session_id });
        }

        if (event.content) {
          set((state) => {
            const messages = [...state.messages];
            const lastIdx = messages.length - 1;
            if (lastIdx >= 0 && messages[lastIdx].role === "assistant") {
              messages[lastIdx] = {
                ...messages[lastIdx],
                // Add newline after each SSE content chunk
                content: messages[lastIdx].content + event.content + "\n",
              };
            }
            return { messages };
          });
        }

        if (event.confirmation) {
          const lastAssistantId = get().messages.filter(m => m.role === "assistant").slice(-1)[0]?.id || "";
          set({
            confirmation: {
              thread_id: event.confirmation.thread_id,
              session_id: event.confirmation.session_id,
              content: event.content || "",
              afterMessageId: lastAssistantId,
            },
          });
        }
      }
    } catch (err) {
      console.error("Workflow SSE error:", err);
      set((state) => {
        const messages = [...state.messages];
        const lastIdx = messages.length - 1;
        if (lastIdx >= 0 && messages[lastIdx].role === "assistant") {
          messages[lastIdx] = {
            ...messages[lastIdx],
            content: messages[lastIdx].content || "Workflow execution failed, please try again.",
          };
        }
        return { messages };
      });
    } finally {
      set({ isLoading: false });
    }
  },

  confirmAction: async (threadId: string, sessionId: string) => {
    set({ confirmation: null, isLoading: true });

    // Add a new assistant message for the confirmation response
    const assistantMessage: Message = {
      id: generateId(),
      role: "assistant",
      content: "",
      timestamp: Date.now(),
    };
    set((state) => ({ messages: [...state.messages, assistantMessage] }));

    try {
      const stream = streamConfirmSSE({
        thread_id: threadId,
        session_id: sessionId,
      });

      for await (const event of stream) {
        if (event.session_id) {
          set({ sessionId: event.session_id });
        }

        if (event.content) {
          set((state) => {
            const messages = [...state.messages];
            const lastIdx = messages.length - 1;
            if (lastIdx >= 0 && messages[lastIdx].role === "assistant") {
              messages[lastIdx] = {
                ...messages[lastIdx],
                // Add newline after each SSE content chunk
                content: messages[lastIdx].content + event.content + "\n",
              };
            }
            return { messages };
          });
        }

        if (event.confirmation) {
          const lastAssistantId = get().messages.filter(m => m.role === "assistant").slice(-1)[0]?.id || "";
          set({
            confirmation: {
              thread_id: event.confirmation.thread_id,
              session_id: event.confirmation.session_id,
              content: event.content || "",
              afterMessageId: lastAssistantId,
            },
          });
        }
      }
    } catch (err) {
      console.error("Confirm SSE error:", err);
      set((state) => {
        const messages = [...state.messages];
        const lastIdx = messages.length - 1;
        if (lastIdx >= 0 && messages[lastIdx].role === "assistant") {
          messages[lastIdx] = {
            ...messages[lastIdx],
            content: messages[lastIdx].content || "Connection error, please try again.",
          };
        }
        return { messages };
      });
    } finally {
      set({ isLoading: false });
    }
  },

  rejectAction: async (_threadId: string, _sessionId: string) => {
    // Simply clear the confirmation state - no API call for rejection
    set({ confirmation: null });

    // Add a system-like message about rejection
    const rejectMessage: Message = {
      id: generateId(),
      role: "assistant",
      content: "Action has been rejected.",
      timestamp: Date.now(),
    };
    set((state) => ({ messages: [...state.messages, rejectMessage] }));
  },
}));
