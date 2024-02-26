import { writable } from "svelte/store";

// Backend
export const config = writable(undefined);
export const user = writable(undefined);

// Frontend
export const db = writable(undefined);
export const chatId = writable("");
export const chats = writable([]);
export const modelfiles = writable([]);
export const settings = writable({});
export const app = writable(false);
export const systemSpeaking = writable(false);
export const showSettings = writable(false);
