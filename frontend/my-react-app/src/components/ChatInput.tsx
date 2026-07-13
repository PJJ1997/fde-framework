import { useState, useRef, useCallback } from "react";
import { SendHorizontal, Play } from "lucide-react";
import { useChatStore } from "@/store/chatStore";

export default function ChatInput() {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isLoading = useChatStore((s) => s.isLoading);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const triggerWorkflow = useChatStore((s) => s.triggerWorkflow);

  const disabled = isLoading;

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    sendMessage(trimmed);
    setText("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [text, disabled, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 4 * 24)}px`;
  }, []);

  return (
    <div className="border-t border-white/10 bg-[#1a1a2e]/95 backdrop-blur-sm px-4 py-3">
      <div className="max-w-3xl mx-auto flex items-end gap-3">
        <button
          onClick={triggerWorkflow}
          disabled={isLoading}
          className="flex-shrink-0 h-10 px-3 rounded-xl bg-violet-600 hover:bg-violet-700 disabled:bg-gray-600 disabled:cursor-not-allowed flex items-center gap-1.5 text-sm text-white transition-colors"
          title="Trigger workflow"
        >
          <Play className="w-4 h-4" />
          <span className="hidden sm:inline">Workflow</span>
        </button>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder={disabled ? "Waiting for response..." : "Type a message..."}
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none bg-[#2d2d4a] text-gray-200 placeholder-gray-500 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-emerald-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ maxHeight: "96px" }}
        />
        <button
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          className="flex-shrink-0 w-10 h-10 rounded-xl bg-emerald-500 hover:bg-emerald-600 disabled:bg-gray-600 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
        >
          <SendHorizontal className="w-5 h-5 text-white" />
        </button>
      </div>
    </div>
  );
}
