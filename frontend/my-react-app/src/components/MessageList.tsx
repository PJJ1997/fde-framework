import { useEffect, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import MessageItem from "./MessageItem";
import ConfirmationMessage from "./ConfirmationMessage";

export default function MessageList() {
  const messages = useChatStore((s) => s.messages);
  const isLoading = useChatStore((s) => s.isLoading);
  const confirmation = useChatStore((s) => s.confirmation);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, confirmation]);

  // Find the index after which the confirmation should be inserted
  const confirmAfterIdx = confirmation
    ? messages.findIndex((m) => m.id === confirmation.afterMessageId)
    : -1;

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-4 py-6 space-y-4"
    >
      {messages.length === 0 && !confirmation && (
        <div className="flex flex-col items-center justify-center h-full text-gray-500 gap-3">
          <div className="w-16 h-16 rounded-full bg-[#2d2d4a] flex items-center justify-center">
            <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <p className="text-lg font-medium text-gray-400">FDE Agent Chat</p>
          <p className="text-sm text-gray-500">Send a message to start the conversation</p>
        </div>
      )}

      {messages.map((msg, idx) => {
        const isLast = idx === messages.length - 1;
        const isStreaming = isLast && msg.role === "assistant" && isLoading && !confirmation;
        return (
          <div key={msg.id}>
            <MessageItem message={msg} isStreaming={isStreaming} />
            {/* Insert confirmation right after the message that triggered it */}
            {confirmAfterIdx === idx && confirmation && (
              <div className="mt-4">
                <ConfirmationMessage />
              </div>
            )}
          </div>
        );
      })}

      <div ref={bottomRef} />
    </div>
  );
}
