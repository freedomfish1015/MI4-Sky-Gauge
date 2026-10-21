// SPDX-License-Identifier: GPL-2.0
/*
 * Lumia RM-940 QDSP6 sound card -- Branch A, build 2 of 2.
 *
 * The real playback topology, replacing the dummy CPU side of
 * wcd9320-lumia-card:
 *
 *   MultiMedia1 FE   q6asm-dais, APR service ASM (7)   PCM-facing session
 *        |  DPCM, via the "SLIMBUS_0_RX Audio Mixer" DAPM control
 *   SLIMBUS_0_RX BE  q6afe-dais, APR service AFE (4)   AFE port 0x4000
 *        |
 *   wcd9320-slim-rx1   codec slave port 16
 *
 * WHY THIS IS A SEPARATE MODULE FROM wcd9320-lumia-card
 *
 * That card is a frozen proof oracle: the RX-callback milestone depends on
 * it, and the prepare-only helper was calibrated against it. It stays exactly
 * as it is. This module is the thing under test; keeping them apart means a
 * failure here cannot be confused with a regression there.
 *
 * They are mutually exclusive at runtime, and ASoC enforces that itself --
 * soc_probe_component() refuses to bind a component to a second card with
 *
 *   "Trying to bind component ... but is already bound to card ..."
 *
 * and returns -ENODEV. No hand-rolled guard is needed here, and one would only
 * duplicate a clearer message.
 *
 * WHY THE LINKS COME FROM DT AND NOT FROM C
 *
 * Measured on boot #155: the front-end DAI is NOT called "MultiMedia1". The
 * q6asm FE component sets .legacy_dai_naming = 1, so with a single declared
 * DAI ASoC uses fmt_single_name() and names it after the DEVICE:
 *
 *   fe200000.remoteproc:smd-edge:apr:service@7:dais
 *
 * A dai_link naming its CPU "MultiMedia1" would silently fail to match. So
 * links are wired with sound-dai phandles and parsed by qcom_snd_parse_of(),
 * which resolves names through the component that owns each of_node and also
 * sets the DPCM flags correctly (dynamic on the FE, no_pcm on the BE).
 *
 * THE CHANNEL MAP COMES FROM THE CODEC
 *
 * q6slim_hw_params() records only rate and bit width; num_channels and
 * ch_mapping[] come solely from q6slim_set_channel_map(). Without the call
 * below, q6afe_dai_prepare() would configure the port with num_channels = 0.
 *
 * Channel 144 on slave port 16 WAS a proposal borrowed from apq8096. It is
 * now hardware evidence: the control-plane milestone had the AFE accept the
 * pairing, and B1 had the ADSP accept CONNECT_SINK and DEF_ACT_CHAN for it,
 * with qcom_slim_ngd_enable_stream() returning 0.
 *
 * So the number now lives where it belongs. The codec reports its own
 * physical mapping through .get_channel_map, and this driver relays it to
 * the AFE. It previously held a second, independent #define of 144 that
 * nothing forced to equal the codec's -- they matched by luck. A divergence
 * would have configured the AFE for one channel and the codec for another,
 * and the symptom would have been a stream that came up cleanly on both
 * sides and carried nothing.
 *
 * The earlier note here said a codec-side channel ABI would be 'the wrong
 * order'. That was correct at the time: the number was unproven. The order
 * was measure first, then encode, and this is the encoding step.
 */

#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

#include <sound/pcm.h>
#include <sound/pcm_params.h>
#include <sound/soc.h>

#include "common.h"

#define DRV_NAME	"wcd9320-lumia-q6"

/*
 * An upper bound for the relay buffers only. This driver deliberately holds
 * no channel numbers of its own -- see the header. The codec side is slave
 * port 16, registers 0x180 and 0x040, proven on every boot since the RX-DAI
 * milestone.
 */
#define LUMIA_MAX_SLIM_CH	8

/*
 * Pin the back end rather than inheriting whatever the front end negotiated.
 * The codec's frozen delta (0x040: 00->05, 0x180: 00->01) was proven at
 * 48 kHz / 1 channel / S16_LE, and this milestone compares against that
 * delta; letting the BE drift would compare against something else.
 */
static int lumia_q6_be_hw_params_fixup(struct snd_soc_pcm_runtime *rtd,
				       struct snd_pcm_hw_params *params)
{
	struct snd_interval *rate =
		hw_param_interval(params, SNDRV_PCM_HW_PARAM_RATE);
	struct snd_interval *channels =
		hw_param_interval(params, SNDRV_PCM_HW_PARAM_CHANNELS);

	rate->min = rate->max = 48000;
	channels->min = channels->max = 1;
	snd_mask_set_format(hw_param_mask(params, SNDRV_PCM_HW_PARAM_FORMAT),
			    SNDRV_PCM_FORMAT_S16_LE);

	return 0;
}

static int lumia_q6_be_hw_params(struct snd_pcm_substream *substream,
				 struct snd_pcm_hw_params *params)
{
	struct snd_soc_pcm_runtime *rtd = snd_soc_substream_to_rtd(substream);
	struct snd_soc_dai *cpu_dai = snd_soc_rtd_to_cpu(rtd, 0);
	struct snd_soc_dai *codec_dai;
	unsigned int rx_ch[LUMIA_MAX_SLIM_CH], tx_ch[LUMIA_MAX_SLIM_CH];
	unsigned int rx_ch_cnt = 0, tx_ch_cnt = 0;
	int ret, i;

	if (substream->stream != SNDRV_PCM_STREAM_PLAYBACK)
		return 0;

	/*
	 * Ask the codec what its channels are, then tell the AFE. This driver
	 * no longer holds an opinion about channel numbers.
	 *
	 * It used to carry its own "#define WCD9320_SLIM_RX1_CH 144" while the
	 * codec carried another, with nothing to keep them equal -- a silent
	 * mismatch would have configured the AFE for one channel and the codec
	 * for a different one, and the symptom would have been a stream that
	 * came up cleanly on both sides and carried nothing. This is the
	 * mainline ownership model, and it is the one sdm845 uses.
	 */
	for_each_rtd_codec_dais(rtd, i, codec_dai) {
		ret = snd_soc_dai_get_channel_map(codec_dai, &tx_ch_cnt, tx_ch,
						  &rx_ch_cnt, rx_ch);
		if (ret == -ENOTSUPP)
			continue;
		if (ret) {
			dev_err(rtd->card->dev,
				"codec %s would not report its channel map: %d\n",
				codec_dai->name, ret);
			return ret;
		}

		if (!rx_ch_cnt || rx_ch_cnt > LUMIA_MAX_SLIM_CH) {
			dev_err(rtd->card->dev,
				"codec %s reported %u receive channels\n",
				codec_dai->name, rx_ch_cnt);
			return -EINVAL;
		}

		ret = snd_soc_dai_set_channel_map(cpu_dai, 0, NULL,
						  rx_ch_cnt, rx_ch);
		if (ret && ret != -ENOTSUPP) {
			dev_err(rtd->card->dev,
				"failed to set the AFE receive channel map: %d\n",
				ret);
			return ret;
		}

		dev_info(rtd->card->dev,
			 "BE hw_params: cpu=%s codec=%s rate=%u ch=%u ch_map={%u} (reported by the codec)\n",
			 cpu_dai->name, codec_dai->name,
			 params_rate(params), params_channels(params),
			 rx_ch[0]);
	}

	return 0;
}

static const struct snd_soc_ops lumia_q6_be_ops = {
	.hw_params = lumia_q6_be_hw_params,
};

/*
 * Static DTS usually lists the FE first. A merged overlay can reverse child
 * insertion order, which qcom_snd_parse_of() preserves. On 6.15 components
 * and their DAPM routes are probed in link order: q6routing needs the MM_DL
 * and MM_UL widgets from q6asm to exist already. Keep FEs before BEs instead
 * of relying on source/overlay child ordering or suppressing route errors.
 */
static void lumia_q6_order_links(struct snd_soc_card *card)
{
	int i, j;

	for (i = 1; i < card->num_links; i++) {
		struct snd_soc_dai_link link = card->dai_link[i];

		if (link.no_pcm)
			continue;
		for (j = i; j > 0 && card->dai_link[j - 1].no_pcm; j--)
			card->dai_link[j] = card->dai_link[j - 1];
		card->dai_link[j] = link;
	}
}

/*
 * qcom_snd_parse_of() marks a link no_pcm exactly when its DT child has BOTH
 * a codec and a platform node, so this is the same test apq8096 uses to find
 * its back ends.
 */
static void lumia_q6_add_be_ops(struct snd_soc_card *card)
{
	struct snd_soc_dai_link *link;
	int i;

	for_each_card_prelinks(card, i, link) {
		if (link->no_pcm) {
			link->be_hw_params_fixup = lumia_q6_be_hw_params_fixup;
			link->ops = &lumia_q6_be_ops;
			dev_info(card->dev, "back end: %s (id %d)\n",
				 link->name, link->id);
		} else {
			/*
			 * A playback front end wants the SINK up before the
			 * SOURCE starts, and stopped after it. The ASoC default
			 * is TRIGGER_PRE, which is the wrong way round at BOTH
			 * ends, because dpcm_fe_dai_do_trigger() reverses the
			 * order for STOP: the FE runs first on START and the BE
			 * first on STOP.
			 *
			 * Measured on r158, with the default: exactly ONE period
			 * completed before the codec's SLIMbus stream was
			 * enabled, and one more after it was disabled -- 960
			 * frames, 20 ms, consumed at each end while the codec
			 * channel was not connected.
			 *
			 * TRIGGER_POST inverts both, because ASoC applies the
			 * same reversal to it. No mainline Qualcomm board sets
			 * this, so they all carry the same 20 ms glitch; we own
			 * this link, and the evidence says to fix it.
			 */
			link->trigger[SNDRV_PCM_STREAM_PLAYBACK] =
				SND_SOC_DPCM_TRIGGER_POST;
			link->trigger[SNDRV_PCM_STREAM_CAPTURE] =
				SND_SOC_DPCM_TRIGGER_POST;
			dev_info(card->dev,
				 "front end: %s (id %d), trigger POST\n",
				 link->name, link->id);
		}
	}
}

static int lumia_q6_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct snd_soc_card *card;
	int ret;

	card = devm_kzalloc(dev, sizeof(*card), GFP_KERNEL);
	if (!card)
		return -ENOMEM;

	card->owner = THIS_MODULE;
	card->dev = dev;
	dev_set_drvdata(dev, card);

	/*
	 * Resolves every sound-dai phandle through the component that owns the
	 * target of_node, and sets the DPCM flags. A codec phandle that cannot
	 * be resolved yet returns -EPROBE_DEFER from here -- which is why a
	 * missing #sound-dai-cells shows up as a card that never registers,
	 * not as a runtime failure later on.
	 */
	ret = qcom_snd_parse_of(card);
	if (ret)
		return dev_err_probe(dev, ret, "failed to parse the DT links\n");

	lumia_q6_order_links(card);
	lumia_q6_add_be_ops(card);

	ret = devm_snd_soc_register_card(dev, card);
	if (ret)
		return dev_err_probe(dev, ret, "failed to register the card\n");

	dev_info(dev, "QDSP6 card registered: %d link(s)\n", card->num_links);
	return 0;
}

static const struct of_device_id lumia_q6_device_id[] = {
	{ .compatible = "nokia,lumia1520-q6-sndcard" },
	{ .compatible = "xiaomi,cancro-taiko-sndcard" },
	{}
};
MODULE_DEVICE_TABLE(of, lumia_q6_device_id);

static struct platform_driver lumia_q6_driver = {
	.probe = lumia_q6_probe,
	.driver = {
		.name = DRV_NAME,
		.of_match_table = lumia_q6_device_id,
	},
};
module_platform_driver(lumia_q6_driver);

MODULE_DESCRIPTION("Nokia Lumia 1520 QDSP6 sound card (WCD9320 over SLIMbus)");
MODULE_LICENSE("GPL v2");
MODULE_VERSION("mi4-q6-link-order1");
