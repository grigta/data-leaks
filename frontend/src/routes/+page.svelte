<script lang="ts">
	import { browser } from '$app/environment';
	import { isAuthenticated, isInitializing } from '$lib/stores/auth';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
</script>

<div class="flex min-h-screen items-center justify-center bg-background">
	{#if browser && $isInitializing}
		<div class="text-center animate-in fade-in duration-300">
			<Skeleton class="h-10 w-96 mb-4 mx-auto" />
			<Skeleton class="h-6 w-80 mb-8 mx-auto" />
			<div class="flex gap-4 justify-center">
				<Skeleton class="h-12 w-24" />
				<Skeleton class="h-12 w-28" />
			</div>
		</div>
	{:else}
		<div class="text-center">
			<h1 class="mb-4 text-4xl font-bold text-foreground">Welcome to SSN Management System</h1>
			<p class="mb-8 text-muted-foreground">
				Secure SSN lookup, reverse search, and fullz purchasing platform.
			</p>
			{#if !$isAuthenticated}
				<div class="flex gap-4 justify-center">
					<Button asChild size="lg">
						<a href="/login">Login</a>
					</Button>
					<Button asChild variant="outline" size="lg">
						<a href="/register">Register</a>
					</Button>
				</div>
			{:else}
				<div class="flex gap-4 justify-center">
					<Button asChild size="lg">
						<a href="/dashboard">Go to Dashboard</a>
					</Button>
				</div>
			{/if}
		</div>
	{/if}
</div>
