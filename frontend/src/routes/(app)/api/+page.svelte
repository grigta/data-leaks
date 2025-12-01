<script lang="ts">
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import Code from '@lucide/svelte/icons/code';
	import { t } from '$lib/i18n';
</script>

<div class="container mx-auto max-w-7xl space-y-6 p-6">
	<Card class="border-2 shadow-lg transition-all duration-300 hover:shadow-xl">
		<CardContent class="flex flex-col items-center space-y-6 p-12 text-center">
			<div class="animate-pulse">
				<Code class="h-20 w-20 text-primary" />
			</div>

			<div class="space-y-3">
				<CardTitle class="text-3xl font-bold">{$t('api.title')}</CardTitle>
				<p class="text-lg text-muted-foreground">
					{$t('api.description')}
				</p>
			</div>

			<Badge variant="secondary" class="px-6 py-2 text-base">
				{$t('api.comingSoon')}
			</Badge>

			<p class="text-sm text-muted-foreground">
				{$t('api.stayTuned')}
			</p>
		</CardContent>
	</Card>
</div>
