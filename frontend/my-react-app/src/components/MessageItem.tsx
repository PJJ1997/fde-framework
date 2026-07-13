import { useEffect, useRef, useState } from "react";
import { Bot, User } from "lucide-react";
import type { Message } from "@/types";

interface MessageItemProps {
  message: Message;
  isStreaming?: boolean;
}

// Typing speed: characters per frame (~60fps → ~1200 chars/sec)
const CHARS_PER_TICK = 20;
const TICK_MS = 16;

export default function MessageItem({ message, isStreaming }: MessageItemProps) {
  const isUser = message.role === "user";
  const contentRef = useRef<HTMLDivElement>(null);

  // Typing effect: track how many characters are "revealed"
  const [revealedLen, setRevealedLen] = useState(0);
  const rafRef = useRef<number>(0);
  const lastContentLen = useRef(0);

  useEffect(() => {
    // For user messages or non-streaming, show everything immediately
    if (isUser || !isStreaming) {
      setRevealedLen(message.content.length);
      return;
    }

    // When new content arrives (content grew), start typing reveal
    if (message.content.length > lastContentLen.current) {
      lastContentLen.current = message.content.length;
    }

    // Animate: gradually increase revealedLen toward content length
    const animate = () => {
      setRevealedLen((prev) => {
        const target = message.content.length;
        if (prev >= target) return target;
        return Math.min(prev + CHARS_PER_TICK, target);
      });
      rafRef.current = requestAnimationFrame(animate);
    };

    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [message.content, isStreaming, isUser]);

  // When streaming ends, instantly reveal all
  useEffect(() => {
    if (!isStreaming) {
      setRevealedLen(message.content.length);
      lastContentLen.current = message.content.length;
    }
  }, [isStreaming, message.content.length]);

  // Render the revealed portion
  const displayContent = isStreaming
    ? message.content.slice(0, revealedLen)
    : message.content;

  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.innerHTML = formatContent(displayContent);
    }
  }, [displayContent]);

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} items-start`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? "bg-blue-600" : "bg-[#2d2d4a]"
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-emerald-400" />
        )}
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[75%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-[#2d2d4a] text-gray-200"
        }`}
      >
        <div ref={contentRef} className="whitespace-pre-wrap break-words">
          {displayContent || ""}
        </div>
        {isStreaming && revealedLen < message.content.length && !message.content && (
          <span className="inline-block w-2 h-4 bg-emerald-400 animate-pulse ml-1" />
        )}
        {isStreaming && revealedLen < message.content.length && message.content && (
          <span className="inline-block w-0.5 h-4 bg-emerald-400 animate-pulse ml-0.5 align-text-bottom" />
        )}
      </div>
    </div>
  );
}

function formatContent(content: string): string {
  // Basic markdown-like formatting
  let html = content
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Code blocks: ```lang\n...\n```
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
    return `<pre class="bg-black/30 rounded-lg p-3 my-2 overflow-x-auto text-xs"><code>${code.trim()}</code></pre>`;
  });

  // Inline code: `...`
  html = html.replace(/`([^`]+)`/g, '<code class="bg-black/30 px-1.5 py-0.5 rounded text-xs">$1</code>');

  // Bold: **...**
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  return html;
}
