<script lang="ts">
  import { v4 as uuidv4 } from "uuid";
  import toast from "svelte-french-toast";

  import { OLLAMA_API_BASE_URL } from "$lib/constants";
  import { onMount, tick } from "svelte";
  import { splitStream } from "$lib/utils";
  import { goto } from "$app/navigation";

  import { config, user, settings, db, chats, chatId } from "$lib/stores";

  import MessageInput from "$lib/components/chat/MessageInput.svelte";
  import Messages from "$lib/components/chat/Messages.svelte";
  import Navbar from "$lib/components/layout/Navbar.svelte";
  import { page } from "$app/stores";

  const socket = new WebSocket("ws://localhost:8080/ws");

  let stopResponseFlag = false;
  let autoScroll = true;
  let isMicrophoneMuted: boolean = false;

  let title = "";
  let prompt = "";
  let systemSpeaking = false;
  let speechRecognitionListening = false;

  let messages = [];
  let history = {
    messages: {},
    currentId: null,
  };

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

    isMicrophoneMuted = await getMicrophoneStatus();
    console.log(`microphone mute status: ${isMicrophoneMuted}`);

    chatId.subscribe(async () => {
      await initNewChat();
    });

    checkWsConnection(socket);
  });
  //////////////////////////
  // Web functions
  //////////////////////////

  const initNewChat = async () => {
    console.log(`chatId: ${$chatId}`);

    autoScroll = true;

    title = "";
    messages = [];
    history = {
      messages: {},
      currentId: null,
    };
  };

  function checkWsConnection(ws: WebSocket) {
    const timer = setInterval(() => {
      if (ws.readyState !== 1) {
        clearInterval(timer);
        console.log("Couldn't connect to websocket. Reloading webpage.");

        location.reload();
      }
      // console.log("connected to websocket");
    }, 30000);
  }

  async function handleMessage(response) {
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
      if (messages.length !== 0) {
        history.messages[messages.at(-1).id].childrenIds.push(userMessageId);
      }

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

      let responseMessageId = uuidv4();
      let responseMessage = {
        parentId: userMessageId,
        role: "assistant",
        id: responseMessageId,
        childrenIds: [],
        content: "",
      };

      history.messages[responseMessageId] = responseMessage;
      history.currentId = responseMessageId;

      if (userMessage.parentId !== null) {
        history.messages[userMessage.parentId].childrenIds = [
          ...history.messages[userMessage.parentId].childrenIds,
          responseMessageId,
        ];
      }
    } else if (response.role === "system") {
      console.log(`system message: ${response.prompt}`);
      if (messages.length !== 0) {
        history.messages[history.currentId].content = response.content;
        history.messages[history.currentId].done = true;
      }
      await tick();

      await $db.updateChatById($chatId, {
        title: title === "" ? "New Chat" : title,
        messages: messages,
        history: history,
      });

      await chats.set(await $db.getChats());
    } else if (response.role === "status") {
      if (response.data === "recognizer_loop:record_begin") {
        speechRecognitionListening = true;
      } else if (response.data === "recognizer_loop:record_end") {
        speechRecognitionListening = false;
      } else if (response.data === "recognizer_loop:audio_output_start") {
        systemSpeaking = true;
      } else if (response.data === "recognizer_loop:audio_output_end") {
        systemSpeaking = false;
      }
    }
  }
  //////////////////////////
  // Ollama functions
  //////////////////////////

  const sendPrompt = async (userPrompt, parentId) => {
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

      stopResponseFlag = false;
    } catch (error) {
      console.log(error);
      if ("detail" in error) {
        toast.error(error.detail);
      }
    }

    await tick();
    if (autoScroll) {
      window.scrollTo({ top: document.body.scrollHeight });
    }

    await $db.updateChatById($chatId, {
      title: title === "" ? "New Chat" : title,
      messages: messages,
      history: history,
    });

    await chats.set(await $db.getChats());
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

  const stopResponse = async () => {
    stopResponseFlag = true;

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

    systemSpeaking = false;
    // console.log("stopResponse");
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

  <MessageInput
    bind:prompt
    bind:autoScroll
    bind:isMuted={isMicrophoneMuted}
    bind:systemSpeaking
    bind:speechRecognitionListening
    suggestionPrompts={[
      {
        title: ["Help me study", "vocabulary for a college entrance exam"],
        content: `Help me study vocabulary: write a sentence for me to fill in the blank, and I'll try to pick the correct option.`,
      },
      {
        title: ["Give me ideas", `for what to do with my kids' art`],
        content: `What are 5 creative things I could do with my kids' art? I don't want to throw them away, but it's also so much clutter.`,
      },
      {
        title: ["Tell me a fun fact", "about the Roman Empire"],
        content: "Tell me a random fun fact about the Roman Empire",
      },
      {
        title: ["Show me a code snippet", `of a website's sticky header`],
        content: `Show me a code snippet of a website's sticky header in CSS and JavaScript.`,
      },
    ]}
    {messages}
    {listenHandler}
    {submitPrompt}
    {stopResponse}
    {microphoneHandler}
  />
</div>
