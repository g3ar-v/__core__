import { v4 as uuidv4 } from "uuid";
import sha256 from "js-sha256";
import { OLLAMA_API_BASE_URL } from "$lib/constants";
import {
  isMicrophoneMuted,
  systemListening,
  systemSpeaking,
} from "$lib/stores";
import toast from "svelte-french-toast";

//////////////////////////
// Web functions
//////////////////////////
export function checkWsConnection(ws: WebSocket) {
  console.log("checking web connection");
  const timer = setInterval(() => {
    if (ws.readyState !== 1) {
      clearInterval(timer);
      toast.error("Couldn't connect to websocket. Reloading webpage.");

      location.reload();
    }
    // console.log("connected to websocket");
  }, 30000);
}

//////////////////////////
// Helper functions
//////////////////////////
export const stopSpeaking = async ($settings) => {
  console.log("Stopping system speech");
  try {
    // TODO: if response is false system speaking == false
    await fetch(
      `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/speech`,
      { method: "DELETE" }
    );
  } catch (error) {
    console.log(error);
    toast.error(error.detail);
  }

  systemSpeaking.set(false);
};

export const getMicrophoneStatus = async (
  $settings
): Promise<boolean | undefined> => {
  try {
    const response = await fetch(
      `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/microphone`,
      {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );
    const microphoneStatusResponse = await response.json();

    return microphoneStatusResponse.message.content;
  } catch (error) {
    toast.error(`Error occurred while fetching microphone status: ${error}`);
  }
};

export const stopListening = async ($settings) => {
  try {
    console.log("stop listening with settings", $settings);
    await fetch(
      `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/listen`,
      { method: "DELETE" }
    );
  } catch (error) {
    console.log(error);
    toast.error(error.detail);
  }

  systemListening.set(false);
};

export const listenHandler = async () => {
  await fetch(`${OLLAMA_API_BASE_URL}v1/voice/listen`, {
    method: "PUT",
  });
};

export const microphoneHandler = async ($settings, $isMicrophoneMuted) => {
  const toggleMicrophoneState = async (state) => {
    const response = await fetch(
      `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/microphone`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ state }),
      }
    );

    if (state === "unmute") {
      console.log("unmuting microphone");
      isMicrophoneMuted.set(false);
    } else {
      console.log("muting microphone");
      isMicrophoneMuted.set(true);
    }
  };

  if ($isMicrophoneMuted) {
    await toggleMicrophoneState("unmute");
  } else {
    await toggleMicrophoneState("mute");
  }
  return $isMicrophoneMuted;
};

export const splitStream = (splitOn) => {
  let buffer = "";
  return new TransformStream({
    transform(chunk, controller) {
      buffer += chunk;
      const parts = buffer.split(splitOn);
      parts.slice(0, -1).forEach((part) => controller.enqueue(part));
      buffer = parts[parts.length - 1];
    },
    flush(controller) {
      if (buffer) controller.enqueue(buffer);
    },
  });
};

export const convertMessagesToHistory = (messages) => {
  let history = {
    messages: {},
    currentId: null,
  };

  let parentMessageId = null;
  let messageId = null;

  for (const message of messages) {
    messageId = uuidv4();

    if (parentMessageId !== null) {
      history.messages[parentMessageId].childrenIds = [
        ...history.messages[parentMessageId].childrenIds,
        messageId,
      ];
    }

    history.messages[messageId] = {
      ...message,
      id: messageId,
      parentId: parentMessageId,
      childrenIds: [],
    };

    parentMessageId = messageId;
  }

  history.currentId = messageId;
  return history;
};

export const extractObjectsbyName = (mainObject, listOptions) => {
  let extractedObjects = {};

  listOptions.forEach((option) => {
    if (mainObject.hasOwnProperty(option)) {
      extractedObjects[option] = mainObject[option];
    }
  });
  return extractedObjects;
};

export const formatContextForBackend = (history: {
  messages: any;
  currentId: string;
}) => {
  return Object.keys(history.messages).map((key) => ({
    role: history.messages[key].role,
    content: history.messages[key].content,
  }));
};

// export const generateTitle = async (prompt: string) => {
//   let error = null;

//   const res = await fetch(`${OLLAMA_API_BASE_URL}/generate`, {
//     method: "POST",
//     headers: {
//       "Content-Type": "text/event-stream",
//       // Authorization: `Bearer ${token}`,
//     },
//     body: JSON.stringify({
//       prompt: `Create a concise, 3-5 word phrase as a header for the following query,
//       strictly adhering to the 3-5 word limit and avoiding the use of the word 'title': ${prompt}`,
//     }),
//   })
//     .then(async (res) => {
//       if (!res.ok) throw await res.json();
//       return res.json();
//     })
//     .catch((err) => {
//       console.log(err);
//       if ("detail" in err) {
//         error = err.detail;
//       }
//       return null;
//     });

//   if (error) {
//     throw error;
//   }

//   return res?.response ?? "New Chat";
// };
export const generateChatTitle = async (_chatId, userPrompt) => {
  // if ($settings.titleAutoGenerate ?? true) {
  console.log("generateChatTitle");

  console.log(
    JSON.stringify({
      content: `Generate a brief 3-5 word title for this question, excluding the term 'title.' Then, please reply with only the title: ${userPrompt}`,
    })
  );
  const res = await fetch(
    `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/system/generate`,
    {
      method: "POST",
      headers: {
        // "Content-Type": "text/event-stream",
        "Content-Type": "application/json",
        // ...($settings.authHeader && {
        //   Authorization: $settings.authHeader,
        // }),
        // ...($user && { Authorization: `Bearer ${localStorage.token}` }),
      },
      body: JSON.stringify({
        content: `Generate a brief 3-5 word title for this question, excluding the term 'title.' Then, please reply with only the title: ${userPrompt}`,
      }),
    }
  )
    .then(async (res) => {
      if (!res.ok) throw await res.json();
      return res.json();
    })
    .catch((error) => {
      if ("detail" in error) {
        toast.error(error.detail);
      }
      console.log(error);
      return null;
    });

  if (res) {
    await setChatTitle(
      _chatId,
      res.response === "" ? "New Chat" : res.response
    );
  }
  // } else {
  //   await setChatTitle(_chatId, `${userPrompt}`);
  // }
};

const regenerateResponse = async () => {
  console.log("regenerateResponse");
  if (messages.length != 0 && messages.at(-1).done == true) {
    messages.splice(messages.length - 1, 1);
    messages = messages;

    let userMessage = messages.at(-1);
    let userPrompt = userMessage.content;

    await sendPrompt(userPrompt, userMessage.id);
  }
};

