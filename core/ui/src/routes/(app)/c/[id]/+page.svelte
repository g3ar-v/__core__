<script lang="ts">
  import { v4 as uuidv4 } from "uuid";
  import toast from "svelte-french-toast";

  import { OLLAMA_API_BASE_URL } from "$lib/constants";
  import { onMount, tick } from "svelte";
  import { convertMessagesToHistory } from "$lib/utils";
  import { goto } from "$app/navigation";

  import { config, user, settings, db, chats, chatId } from "$lib/stores";

  import MessageInput from "$lib/components/chat/MessageInput.svelte";
  import Messages from "$lib/components/chat/Messages.svelte";
  import ModelSelector from "$lib/components/chat/ModelSelector.svelte";
  import Navbar from "$lib/components/layout/Navbar.svelte";
  import { page } from "$app/stores";

  // const socket = new WebSocket("ws://localhost:8080/ws");

  let loaded = false;
  let stopResponseFlag = false;
  let autoScroll = true;
  let isMuted: boolean = false;

  let title = "";
  let prompt = "";
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

  //////////////////////////
  // Web functions
  //////////////////////////

  const loadChat = async () => {
    await chatId.set($page.params.id);
    const chat = await $db.getChatById($chatId);

    if (chat) {
      console.log($chatId + ": chat exists");

      history =
        (chat?.history ?? undefined) !== undefined
          ? chat.history
          : convertMessagesToHistory(chat.messages);
      console.log("history: " + history);
      title = chat.title;

      await settings.set({
        ...$settings,
        system: chat.system ?? $settings.system,
        options: chat.options ?? $settings.options,
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
        console.log("Couldn't connect to websocket. Reloading webpage.");

        location.reload();
      }
      // console.log("connected to websocket");
    }, 30000);
  }

  function handleMessage(response: Object) {
    if (response.type === "user") {
      console.log(`user message: ${response.prompt}`);
      let userMessageId = uuidv4();
      let userMessage = {
        id: userMessageId,
        parentId: messages.length !== 0 ? messages.at(-1).id : null,
        childrenIds: [],
        role: "user",
        content: response.prompt,
      };
      if (messages.length !== 0) {
        history.messages[messages.at(-1).id].childrenIds.push(userMessageId);
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
        history.messages[parentId].childrenIds = [
          ...history.messages[parentId].childrenIds,
          responseMessageId,
        ];
      }
    } else if (response.type === "system") {
      console.log(`system message: ${response.prompt}`);
      if (messages.length !== 0) {
        history.messages[history.currentId].content = response.prompt;
        history.messages[history.currentId].done = true;
      }
    } else if (response.type === "status") {
      if (response.data === "recognizer_loop:record_begin") {
        speechRecognitionListening = true;
      } else if (response.data === "recognizer_loop:record_end") {
        speechRecognitionListening = false;
      }
    }
  }
  //////////////////////////
  // Ollama functions
  //////////////////////////

  const sendPrompt = async (userPrompt, parentId) => {
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
      await setChatTitle($chatId, userPrompt);
    }
    await chats.set(await $db.getChats());
  };

  // const sendPromptCore = async (userPrompt, parentId) => {
  //   console.log(`send to core_backend: ${userPrompt}`);
  //   let responseMessageId = uuidv4();
  //
  //   let responseMessage = {
  //     parentId: parentId,
  //     role: "assistant",
  //     id: responseMessageId,
  //     childrenIds: [],
  //     content: "",
  //   };
  //   //
  //   history.messages[responseMessageId] = responseMessage;
  //   history.currentId = responseMessageId;
  //   if (parentId !== null) {
  //     history.messages[parentId].childrenIds = [
  //       ...history.messages[parentId].childrenIds,
  //       responseMessageId,
  //     ];
  //   }
  //
  //   await tick();
  //
  //   window.scrollTo({ top: document.body.scrollHeight });
  //
  //   const res = await fetch(
  //     `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/voice/utterance`,
  //     {
  //       method: "POST",
  //       headers: {
  //         "Content-Type": "application/json",
  //         // ...($settings.authHeader && { Authorization: $settings.authHeader }),
  //         // ...($user && { Authorization: `Bearer ${localStorage.token}` })
  //       },
  //       body: JSON.stringify({
  //         prompt: userPrompt,
  //       }),
  //     }
  //   );
  //   try {
  //     const responseJson = await res.json();
  //     if ("detail" in responseJson) {
  //       throw responseJson;
  //     }
  //     console.log(`response: ${responseJson}`);
  //     responseMessage.content = responseJson.message.content;
  //     messages = messages;
  //     responseMessage.done = true;
  //     // console.log(``)
  //
  //     stopResponseFlag = false;
  //   } catch (error) {
  //     console.log(error);
  //     if ("detail" in error) {
  //       toast.error(error.detail);
  //     }
  //   }
  //
  //   await tick();
  //   if (autoScroll) {
  //     window.scrollTo({ top: document.body.scrollHeight });
  //   }
  //
  //   await $db.updateChatById($chatId, {
  //     title: title === "" ? "New Chat" : title,
  //     messages: messages,
  //     history: history,
  //   });
  // };

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

  const stopResponse = () => {
    stopResponseFlag = true;
    console.log("stopResponse");
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
  const getMicrophoneStatus = async (): Promise<boolean> => {
    try {
      const response = await fetch(
        `${
          $settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL
        }v1/voice/microphone/status`,
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
    if (isMuted == true) {
      console.log("unmuting microphone");
      await fetch(
        `${
          $settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL
        }v1/voice/microphone/unmute`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );
      isMuted = false;
    } else {
      await fetch(
        `${
          $settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL
        }v1/voice/microphone/mute`,
        {
          method: "PUT",
        }
      );
      console.log("muting microphone");
      isMuted = true;
      // console.log('response: ' + res.body);
    }
    return isMuted;
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
      bind:isMuted
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
      {microphoneHandler}
    />
  </div>
{/if}
