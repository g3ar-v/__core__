<script lang="ts">
  import { v4 as uuidv4 } from "uuid";
  import toast from "svelte-french-toast";

  import { OLLAMA_API_BASE_URL } from "$lib/constants";
  import { onMount, tick } from "svelte";

  import {
    settings,
    db,
    chats,
    chatId,
    systemSpeaking,
    isMicrophoneMuted,
    systemListening,
  } from "$lib/stores";
  import {
    getMicrophoneStatus,
    checkWsConnection,
    formatContextForBackend,
  } from "$lib/utils";

  import MessageInput from "$lib/components/chat/MessageInput.svelte";
  import Messages from "$lib/components/chat/Messages.svelte";
  import Navbar from "$lib/components/layout/Navbar.svelte";
  import type { AnyNode } from "postcss";

  const socket = new WebSocket("ws://localhost:8081");

  let autoScroll = true;

  let title = "";
  let prompt = "";
  // let speechRecognitionListening = false;

  let messages: any[] = [];
  let history: {
    messages: any;
    currentId: string | null;
  } = {
    messages: {},
    currentId: null,
  };
  let systemMessage = {};

  // Update messages based on history if currentId is not null
  $: if (history.currentId !== null) {
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

  onMount(async () => {
    await chatId.set(uuidv4());
    // await history.loadChats();

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

    // TODO: extract to function for both page.svelte
    let microphoneStatus = await getMicrophoneStatus($settings);
    if (microphoneStatus !== undefined) {
      isMicrophoneMuted.set(microphoneStatus);
      console.log(`microphone mute status: ${$isMicrophoneMuted}`);
    } else {
      console.error("Failed to get microphone status.");
    }

    chatId.subscribe(async () => {
      await initNewChat();
    });

    const formattedHistory = formatContextForBackend(history);
    console.log("formatted History: " + formattedHistory);
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

    checkWsConnection(socket);
  });
  //////////////////////////
  // Web functions
  //////////////////////////

  const initNewChat = async () => {
    console.log(`new chatId: ${$chatId}`);

    autoScroll = true;

    title = "";
    messages = [];
    history = {
      messages: {},
      currentId: null,
    };

    const formattedHistory = formatContextForBackend(history);
    console.log("formatted History: " + formattedHistory);
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
  };

  // TODO: extract duplicate code on adding messages to chat history
  async function handleMessage(response: {
    role: string;
    content: any;
    data: string;
    type: string;
    start: any;
    end: any;
  }) {
    if (response.role === "user") {
      // console.log(`user message: ${response.content}`);
      let userMessageId = uuidv4();
      let userMessage = {
        id: userMessageId,
        parentId: messages.length !== 0 ? messages.at(-1).id : null,
        childrenIds: [],
        role: "user",
        content: response.content,
      };

      // This code checks if there are any existing messages in the chat history and
      // updates the childrenIds of the last message with the newly generated user
      // message ID.
      // if (messages.length !== 0) {
      //   history.messages[messages.at(-1).id].childrenIds.push(userMessageId);
      // }

      if (messages.length == 0) {
        await $db.createNewChat({
          id: $chatId,
          title: "New Chat",
          messages: messages,
          history: history,
        });
      }

      history.messages[userMessageId] = userMessage;
      history.currentId = userMessageId;
      await tick();
      console.log("autoscroll: ", autoScroll);
      if (autoScroll) {
        window.scrollTo({ top: document.body.scrollHeight });
      }

      await $db.updateChatById($chatId, {
        title: title === "" ? "New Chat" : title,
        messages: messages,
        history: history,
      });
      updateChatAndScroll(response.content);
    } else if (response.role === "assistant") {
      if (response.start) {
        let systemMessageId = uuidv4();
        systemMessage = {
          parentId: messages.length !== 0 ? messages.at(-1).id : null,
          role: "assistant",
          id: systemMessageId,
          childrenIds: [],
          content: "",
        };
        // console.log("system message id: ", systemMessageId);

        // console.log("history.currentId: ", history.currentId);
      } else if (response.content) {
        systemMessage.content += response.content;
        history.messages[systemMessage.id] = systemMessage;
        history.currentId = systemMessage.id;

        // console.log(
        //   `system message: ${history.messages[systemMessage.id].content}`
        // );
      } else if (response.end) {
        systemMessage.done = true;
        history.messages[history.currentId] = systemMessage;

        await $db.updateChatById($chatId, {
          title: title === "" ? "New Chat" : title,
          messages: messages,
          history: history,
        });
      }

      if (messages.length == 0) {
        await $db.createNewChat({
          id: $chatId,
          title: "New Chat",
          messages: messages,
          history: history,
        });
      }

      // updateChatAndScroll(response.content);
    } else if (response.role === "status") {
      if (response.data === "recognizer_loop:record_begin") {
        systemListening.set(true);
      } else if (response.data === "recognizer_loop:record_end") {
        systemListening.set(false);
      } else if (response.data === "recognizer_loop:audio_output_start") {
        systemSpeaking.set(true);
        console.log("system speaking");
      } else if (response.data === "recognizer_loop:audio_output_end") {
        systemSpeaking.set(false);
        console.log("system done speaking");
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
          role: "user",
          content: userPrompt,
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
    updateChatAndScroll(userPrompt);
  };

  const submitPrompt = async (userPrompt) => {
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

      // if (messages.length !== 0) {
      //   history.messages[messages.at(-1).id].childrenIds.push(userMessageId);
      // }

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

  const updateChatAndScroll = async (userPrompt) => {
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

  const generateChatTitle = async (_chatId, userPrompt) => {
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

  const setChatTitle = async (_chatId, _title) => {
    await $db.updateChatById(_chatId, { title: _title });
    if (_chatId === $chatId) {
      title = _title;
    }
  };
  const scrollToBottom = () => {
    const element = document.getElementById("messages-container");
    element.scrollTop = element.scrollHeight;
  };
</script>

<svelte:window
  on:scroll={(e) => {
    autoScroll =
      window.innerHeight + window.scrollY >= document.body.offsetHeight - 40;
  }}
/>

<Navbar {title} />
<div class="min-h-screen w-full flex justify-center">
  <div class=" py-2.5 flex flex-col justify-between w-full">
    <div class=" h-full mt-10 mb-32 w-full flex flex-col">
      <Messages bind:history bind:messages bind:autoScroll {sendPrompt} />
    </div>
  </div>

  <MessageInput bind:prompt bind:autoScroll {messages} {submitPrompt} />
</div>
