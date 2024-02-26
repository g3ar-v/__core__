<script lang="ts">
  import { v4 as uuidv4 } from "uuid";
  import toast from "svelte-french-toast";

  import { OLLAMA_API_BASE_URL } from "$lib/constants";
  import { onMount, tick } from "svelte";
  import {
    convertMessagesToHistory,
    formatContextForBackend,
  } from "$lib/utils";
  import { goto } from "$app/navigation";

  import { settings, db, chats, chatId, systemSpeaking } from "$lib/stores";

  import MessageInput from "$lib/components/chat/MessageInput.svelte";
  import Messages from "$lib/components/chat/Messages.svelte";
  import Navbar from "$lib/components/layout/Navbar.svelte";
  import { page } from "$app/stores";
  // import { update } from "svelte-french-toast/dist/core/store";

  const socket = new WebSocket("ws://localhost:8080/ws");

  let loaded = false;
  let stopResponseFlag = false;
  let autoScroll = true;
  let isMicrophoneMuted: boolean = false;

  let title = "";
  let prompt = "";
  let speechRecognitionListening = false;

  let messages: any[] = [];
  let history: {
    messages: any;
    currentId: any;
  } = {
    messages: {},
    currentId: null,
  };

  // Update messages based on history if currentId is not null
  $: if (history.currentId !== null) {
    // console.log("history.currentId", history.currentId);
    let _messages = [];

    let currentMessage = history.messages[history.currentId];
    while (currentMessage !== null) {
      _messages.unshift({ ...currentMessage });
      currentMessage =
        currentMessage.parentId !== null
          ? history.messages[currentMessage.parentId]
          : null;
    }
    messages = _messages;
  } else {
    // Reset messages if currentId is null
    messages = [];
  }

  $: if ($page.params.id) {
    (async () => {
      let chat = await loadChat();

      await tick();
      if (chat) {
        loaded = true;
      } else {
        await goto("/");
      }
    })();
  }

  onMount(async () => {
    socket.onopen = (event) => {
      console.log("WebSocket is open now.");
    };
    socket.onerror = (event) => {
      console.error("WebSocket error observed:", event);
    };
    socket.onmessage = (event) => {
      // console.log("Received data from server:", event.data);
      let response = JSON.parse(event.data);
      handleMessage(response);
    };
    window.addEventListener("beforeunload", function () {
      socket.close();
    });

    let microphoneStatus = await getMicrophoneStatus();
    if (microphoneStatus !== undefined) {
      isMicrophoneMuted = microphoneStatus;
      console.log(`microphone mute status: ${isMicrophoneMuted}`);
    } else {
      console.error("Failed to get microphone status.");
    }
    checkWsConnection(socket);
  });

  //////////////////////////
  // Web functions
  //////////////////////////

  const loadChat = async () => {
    await chatId.set($page.params.id);
    const chat = await $db.getChatById($chatId);

    // console.log("chat: " + JSON.stringify(chat, null, 4));
    console.log("chat", chat);
    if (chat) {
      // console.log($chatId + ": chat exists");

      history =
        (chat?.history ?? undefined) !== undefined
          ? chat.history
          : convertMessagesToHistory(chat.messages);
      title = chat.title;

      const formattedHistory = formatContextForBackend(history);
      await fetch(
        `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/context`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ context: formattedHistory }),
        }
      );
      // console.log(formattedHistory);
      await settings.set({
        ...$settings,
      });
      autoScroll = true;

      await tick();
      if (messages.length > 0) {
        history.messages[messages.at(-1).id].done = true;
      }
      await tick();

      return chat;
    } else {
      return null;
    }
  };

  function checkWsConnection(ws: WebSocket) {
    const timer = setInterval(() => {
      if (ws.readyState !== 1) {
        clearInterval(timer);
        toast.error("Couldn't connect to websocket. Reloading webpage.");

        location.reload();
      }
      // console.log("connected to websocket");
    }, 30000);
  }

  async function handleMessage(response: {
    role: string;
    content: any;
    data: string;
  }) {
    if (response.role === "user") {
      console.log(`user message: ${response.content}`);
      let userMessageId = uuidv4();
      let userMessage = {
        id: userMessageId,
        parentId: messages.length !== 0 ? messages.at(-1).id : null,
        childrenIds: [],
        role: "user",
        content: response.content,
      };
      // if (messages.length !== 0) {
      //   history.messages[messages.at(-1).id].childrenIds.push(userMessageId);
      // }

      history.messages[userMessageId] = userMessage;
      history.currentId = userMessageId;
      updateChatAndScroll(response.content);
    } else if (response.role === "system") {
      console.log(`system message: ${response.content}`);
      let systemMessageId = uuidv4();
      let systemMessage = {
        parentId: messages.length !== 0 ? messages.at(-1).id : null,
        role: "assistant",
        id: systemMessageId,
        childrenIds: [],
        content: response.content,
      };

      // let previousMessage = messages.at(-1);
      history.messages[systemMessageId] = systemMessage;
      history.currentId = systemMessageId;
      updateChatAndScroll(response.content);
    } else if (response.role === "status") {
      if (response.data === "recognizer_loop:record_begin") {
        speechRecognitionListening = true;
        // NOTE: should the websocket send back data or just a request sent to the backend
      } else if (response.data === "recognizer_loop:record_end") {
        speechRecognitionListening = false;
      } else if (response.data === "recognizer_loop:audio_output_start") {
        systemSpeaking.set(true);
      } else if (response.data === "recognizer_loop:audio_output_end") {
        systemSpeaking.set(false);
      }
    }
  }
  //////////////////////////
  // Ollama functions
  //////////////////////////

  const sendPrompt = async (
    userPrompt: any,
    parentId: string | number | null
  ) => {
    // await sendPromptCore(userPrompt, parentId);

    console.log(`send to core_backend: ${userPrompt}`);
    let responseMessageId = uuidv4();

    let responseMessage = {
      parentId: parentId,
      role: "assistant",
      id: responseMessageId,
      childrenIds: [],
      content: "",
    };
    //
    history.messages[responseMessageId] = responseMessage;
    history.currentId = responseMessageId;
    if (parentId !== null) {
      history.messages[parentId].childrenIds = [
        ...history.messages[parentId].childrenIds,
        responseMessageId,
      ];
    }

    await tick();

    window.scrollTo({ top: document.body.scrollHeight });

    const res = await fetch(
      `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/utterance`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // ...($settings.authHeader && { Authorization: $settings.authHeader }),
          // ...($user && { Authorization: `Bearer ${localStorage.token}` })
        },
        body: JSON.stringify({
          prompt: userPrompt,
        }),
      }
    );
    try {
      const responseJson = await res.json();
      if ("detail" in responseJson) {
        throw responseJson;
      }
      console.log(`response: ${responseJson}`);
      responseMessage.content = responseJson.message.content;
      messages = messages;
      responseMessage.done = true;
      // console.log(``)
    } catch (error) {
      console.log(error);
      if ("detail" in error) {
        toast.error(error.detail);
      }
    }

    await updateChatAndScroll(userPrompt);
  };

  const submitPrompt = async (userPrompt: any) => {
    console.log("submitPrompt");

    if (messages.length != 0 && messages.at(-1).done != true) {
      console.log("wait");
    } else {
      document.getElementById("chat-textarea").style.height = "";

      let userMessageId = uuidv4();
      let userMessage = {
        id: userMessageId,
        parentId: messages.length !== 0 ? messages.at(-1).id : null,
        childrenIds: [],
        role: "user",
        content: userPrompt,
      };

      if (messages.length !== 0) {
        history.messages[messages.at(-1).id].childrenIds.push(userMessageId);
      }

      history.messages[userMessageId] = userMessage;
      history.currentId = userMessageId;

      //Wait until history/message have been updated
      await tick();

      prompt = "";

      if (messages.length == 0) {
        await $db.createNewChat({
          id: $chatId,
          title: "New Chat",
          messages: messages,
          history: history,
        });
      }

      setTimeout(() => {
        window.scrollTo({
          top: document.body.scrollHeight,
          behavior: "smooth",
        });
      }, 50);

      await sendPrompt(userPrompt, userMessageId);
    }
  };

  const stopSpeaking = async () => {
    stopResponseFlag = true;

    console.log("stopping sytem speech");
    try {
      // TODO: if response is false system speaking == false
      await fetch(
        `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/speech`,
        { method: "DELETE" }
      );
    } catch (error) {
      // console.log(error);
      toast.error(error.detail);
    }

    systemSpeaking.set(true);
  };

  const updateChatAndScroll = async (userPrompt) => {
    await tick();
    if (autoScroll) {
      window.scrollTo({ top: document.body.scrollHeight });
    }

    await $db.updateChatById($chatId, {
      title: title === "" ? "New Chat" : title,
      messages: messages,
      history: history,
    });

    stopResponseFlag = false;

    await tick();
    if (autoScroll) {
      window.scrollTo({ top: document.body.scrollHeight });
    }

    if (messages.length == 2) {
      window.history.replaceState(history.state, "", `/c/${$chatId}`);
      await generateChatTitle($chatId, userPrompt);
    }
    await chats.set(await $db.getChats());
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
  const generateChatTitle = async (_chatId, userPrompt) => {
    // if ($settings.titleAutoGenerate ?? true) {
    console.log("generateChatTitle");

    const res = await fetch(
      `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/system/generate`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // ...($settings.authHeader && {
          //   Authorization: $settings.authHeader,
          // }),
          // ...($user && { Authorization: `Bearer ${localStorage.token}` }),
        },
        body: JSON.stringify({
          prompt: `Generate a brief 3-5 word title for this question, excluding the term 'title.' Then, please reply with only the title: ${userPrompt}`,
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

  const stopListening = async () => {
    try {
      await fetch(
        `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/listen`,
        { method: "DELETE" }
      );
    } catch (error) {
      console.log(error);
      toast.error(error.detail);
    }

    speechRecognitionListening = false;
  };

  // NOTE: what would be the right return type if there's an error in getting the
  // microphone status
  const getMicrophoneStatus = async (): Promise<boolean | undefined> => {
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

  // TODO: should the fetch method have throws and catch blocks
  const microphoneHandler = async () => {
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
        isMicrophoneMuted = false;
      } else {
        console.log("muting microphone");
        isMicrophoneMuted = true;
      }
    };

    if (isMicrophoneMuted == true) {
      await toggleMicrophoneState("unmute");
    } else {
      await toggleMicrophoneState("mute");
    }
    return isMicrophoneMuted;
  };

  //TODO: implement a handler to prevent button spams
  const listenHandler = async () => {
    await fetch(`${OLLAMA_API_BASE_URL}v1/voice/listen`, {
      method: "PUT",
    });
  };

  const setChatTitle = async (_chatId, _title) => {
    await $db.updateChatById(_chatId, { title: _title });
    if (_chatId === $chatId) {
      title = _title;
    }
  };
</script>

<svelte:window
  on:scroll={(e) => {
    autoScroll =
      window.innerHeight + window.scrollY >= document.body.offsetHeight - 40;
  }}
/>

{#if loaded}
  <Navbar {title} />
  <div class="min-h-screen w-full flex justify-center">
    <div class=" py-2.5 flex flex-col justify-between w-full">
      <div class=" h-full mt-10 mb-32 w-full flex flex-col">
        <Messages bind:history bind:messages bind:autoScroll {sendPrompt} />
      </div>
    </div>

    <MessageInput
      bind:prompt
      bind:autoScroll
      bind:isMicrophoneMuted
      bind:speechRecognitionListening
      {messages}
      {listenHandler}
      {stopListening}
      {submitPrompt}
      {stopSpeaking}
      {microphoneHandler}
    />
  </div>
{/if}
