<script>
  import { page } from "$app/stores";
</script>

<div
  class=" bg-white dark:bg-gray-800 min-h-screen flex items-center justify-center"
>
  <div class="m-auto my-10 dark:text-gray-400 text-3xl font-semibold">
    {$page.status}: {$page.error.message}
  </div>
</div>
