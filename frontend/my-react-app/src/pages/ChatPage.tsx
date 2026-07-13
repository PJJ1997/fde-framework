import MessageList from "@/components/MessageList";
import ChatInput from "@/components/ChatInput";

export default function ChatPage() {
  return (
    <div className="flex flex-col h-dvh bg-[#1a1a2e] text-gray-100">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-white/10 bg-[#1a1a2e]/95 backdrop-blur-sm px-4 py-3">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
            <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-gray-100">FDE Agent</h1>
            <p className="text-xs text-gray-500">AI-Powered Development Assistant</p>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="max-w-3xl mx-auto w-full flex-1 min-h-0 flex flex-col">
          <MessageList />
        </div>
      </div>

      {/* Input */}
      <ChatInput />
    </div>
  );
}
