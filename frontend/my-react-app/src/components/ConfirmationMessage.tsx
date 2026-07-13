import { useChatStore } from "@/store/chatStore";
import { Bot, ShieldAlert, Check, X } from "lucide-react";

export default function ConfirmationMessage() {
  const confirmation = useChatStore((s) => s.confirmation);
  const confirmAction = useChatStore((s) => s.confirmAction);
  const rejectAction = useChatStore((s) => s.rejectAction);

  if (!confirmation) return null;

  return (
    <div className="flex gap-3 flex-row items-start">
      {/* Avatar — same as AI messages */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#2d2d4a] flex items-center justify-center">
        <Bot className="w-4 h-4 text-emerald-400" />
      </div>

      {/* Bubble */}
      <div className="max-w-[75%] rounded-xl bg-[#2d2d4a] text-gray-200 overflow-hidden">
        {/* Warning header */}
        <div className="flex items-center gap-2 px-4 pt-3 pb-2">
          <ShieldAlert className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <span className="text-xs font-medium text-amber-400 uppercase tracking-wide">
            Confirmation Required
          </span>
        </div>

        {/* Content */}
        <div className="px-4 pb-3 text-sm leading-relaxed whitespace-pre-wrap break-words">
          {confirmation.content || "The agent is requesting permission to proceed with an action."}
        </div>

        {/* Action buttons */}
        <div className="flex border-t border-white/10">
          <button
            onClick={() => rejectAction(confirmation.thread_id, confirmation.session_id)}
            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm text-gray-400 hover:bg-white/5 hover:text-gray-200 transition-colors border-r border-white/10"
          >
            <X className="w-3.5 h-3.5" />
            Reject
          </button>
          <button
            onClick={() => confirmAction(confirmation.thread_id, confirmation.session_id)}
            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm text-emerald-400 hover:bg-emerald-500/10 hover:text-emerald-300 transition-colors"
          >
            <Check className="w-3.5 h-3.5" />
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
