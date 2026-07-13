import type { ChatRequest, ConfirmRequest, SSEData, ConversationsResponse } from "@/types";

export async function* streamChatSSE(
  request: ChatRequest
): AsyncGenerator<SSEData> {
  const response = await fetch("/api/chat_sse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const jsonStr = trimmed.slice(6);
      if (!jsonStr) continue;
      try {
        const data: SSEData = JSON.parse(jsonStr);
        yield data;
      } catch {
        // skip malformed JSON
      }
    }
  }

  // Process remaining buffer
  if (buffer.trim().startsWith("data: ")) {
    const jsonStr = buffer.trim().slice(6);
    if (jsonStr) {
      try {
        const data: SSEData = JSON.parse(jsonStr);
        yield data;
      } catch {
        // skip
      }
    }
  }
}

export async function* streamConfirmSSE(
  request: ConfirmRequest
): AsyncGenerator<SSEData> {
  const response = await fetch("/api/actions/confirm_sse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Confirm request failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const jsonStr = trimmed.slice(6);
      if (!jsonStr) continue;
      try {
        const data: SSEData = JSON.parse(jsonStr);
        yield data;
      } catch {
        // skip
      }
    }
  }

  if (buffer.trim().startsWith("data: ")) {
    const jsonStr = buffer.trim().slice(6);
    if (jsonStr) {
      try {
        const data: SSEData = JSON.parse(jsonStr);
        yield data;
      } catch {
        // skip
      }
    }
  }
}

export async function fetchConversations(
  sessionId: string
): Promise<ConversationsResponse> {
  const response = await fetch(
    `/api/conversations?session_id=${encodeURIComponent(sessionId)}`
  );
  if (!response.ok) {
    throw new Error(`Fetch conversations failed: ${response.status}`);
  }
  return response.json();
}
