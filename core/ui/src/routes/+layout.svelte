<script>
  import { onMount, tick } from "svelte";
  import { config } from "$lib/stores";
  import { goto } from "$app/navigation";
  import { WEBUI_API_BASE_URL } from "$lib/constants";
  import toast, { Toaster } from "svelte-french-toast";

  import "../app.css";
  import "../tailwind.css";

  let loaded = false;
  let timeout = 10000;

  function checkBackendConnection() {
    const timer = setInterval(() => {
      if (!loaded) {
        // console.log("Couldn't connect to bckend. Reloading webpage.");

        clearInterval(timer);
        location.reload();
      }
    }, timeout);
  }

  onMount(async () => {
    const resBackend = await fetch(`${WEBUI_API_BASE_URL}/status`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    })
      .then(async (res) => {
        // console.log(res);
        if (!res.ok) {
          throw await res.json();
        } else {
          await tick();
          loaded = true;
          toast.success("connected to backend");
        }
        return res.json();
      })
      .catch((error) => {
        console.log(error);
        toast.error("Can't connect to backend");
        // console.log("timeout: " + timeout);

        checkBackendConnection();
        return null;
      });

    console.log(`backend result: ${resBackend}`);
    await config.set(resBackend);

    // if ($config) {
    //   if ($config.auth) {
    //     if (localStorage.token) {
    //       const res = await fetch(`${WEBUI_API_BASE_URL}/auths`, {
    //         method: "GET",
    //         headers: {
    //           "Content-Type": "application/json",
    //           Authorization: `Bearer ${localStorage.token}`,
    //         },
    //       })
    //         .then(async (res) => {
    //           if (!res.ok) throw await res.json();
    //           return res.json();
    //         })
    //         .catch((error) => {
    //           console.log(error);
    //           toast.error(error.detail);
    //           return null;
    //         });
    //
    //       if (res) {
    //         await user.set(res);
    //       } else {
    //         localStorage.removeItem("token");
    //         await goto("/auth");
    //       }
    //     } else {
    //       await goto("/auth");
    //     }
    //   }
    // }
  });
</script>

<svelte:head>
  <title>VASCO</title>
</svelte:head>
<Toaster />

{#if $config !== undefined && loaded}
  <slot />
{:else}
  <!-- TODO: create can't access backend page -->
  <div class="dark:bg-gray-800 h-screen flex items-center justify-center">
  </div>
{/if}
