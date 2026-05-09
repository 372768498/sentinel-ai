import { appEnv, assertServerEnv } from "@/lib/env";

type CreateInviteLinkOptions = {
  expireSeconds?: number;
  memberLimit?: number;
  name?: string;
};

type TelegramApiResponse<T> = {
  ok: boolean;
  result?: T;
  description?: string;
  error_code?: number;
};

type ChatInviteLink = {
  invite_link: string;
  creator: { id: number; is_bot: boolean; first_name: string };
  creates_join_request: boolean;
  is_primary: boolean;
  is_revoked: boolean;
  name?: string;
  expire_date?: number;
  member_limit?: number;
};

type ChatMember = {
  status: "creator" | "administrator" | "member" | "restricted" | "left" | "kicked";
  user: { id: number };
};

async function callTelegramApi<T>(method: string, params: Record<string, unknown>): Promise<T> {
  const token = assertServerEnv("TELEGRAM_BOT_TOKEN", appEnv.telegramBotToken);
  const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    cache: "no-store"
  });

  const payload = (await response.json()) as TelegramApiResponse<T>;

  if (!response.ok || !payload.ok || payload.result === undefined) {
    throw new Error(
      `Telegram API ${method} failed: ${payload.error_code ?? response.status} ${payload.description ?? ""}`.trim()
    );
  }

  return payload.result;
}

export async function createVipInviteLink(options: CreateInviteLinkOptions = {}) {
  const chatId = assertServerEnv("TELEGRAM_GROUP_ID_VIP", appEnv.telegramGroupIdVip);
  const memberLimit = options.memberLimit ?? 1;
  const expireSeconds = options.expireSeconds ?? 60 * 60 * 24 * 7;
  const expireDate = Math.floor(Date.now() / 1000) + expireSeconds;

  const link = await callTelegramApi<ChatInviteLink>("createChatInviteLink", {
    chat_id: chatId,
    expire_date: expireDate,
    member_limit: memberLimit,
    name: options.name ?? `pro-${Date.now()}`
  });

  return {
    inviteLink: link.invite_link,
    expireDate: link.expire_date ?? expireDate,
    memberLimit: link.member_limit ?? memberLimit
  };
}

export async function revokeInviteLink(inviteLink: string) {
  const chatId = assertServerEnv("TELEGRAM_GROUP_ID_VIP", appEnv.telegramGroupIdVip);

  return callTelegramApi<ChatInviteLink>("revokeChatInviteLink", {
    chat_id: chatId,
    invite_link: inviteLink
  });
}

export async function kickFromVipGroup(telegramUserId: string | number) {
  const chatId = assertServerEnv("TELEGRAM_GROUP_ID_VIP", appEnv.telegramGroupIdVip);

  return callTelegramApi<boolean>("banChatMember", {
    chat_id: chatId,
    user_id: Number(telegramUserId),
    until_date: Math.floor(Date.now() / 1000) + 60
  });
}

export async function getVipMember(telegramUserId: string | number) {
  const chatId = assertServerEnv("TELEGRAM_GROUP_ID_VIP", appEnv.telegramGroupIdVip);

  return callTelegramApi<ChatMember>("getChatMember", {
    chat_id: chatId,
    user_id: Number(telegramUserId)
  });
}

export async function sendBotMessage(chatId: string | number, text: string) {
  return callTelegramApi<{ message_id: number }>("sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    disable_web_page_preview: true
  });
}
