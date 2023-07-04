from transformers import T5ForConditionalGeneration

class MyT5Model(T5ForConditionalGeneration):
    def __init__(self, config):
        super().__init__(config)

    def forward(self, input_ids, attention_mask=None, decoder_input_ids=None, decoder_attention_mask=None, lm_labels=None):
        # 自定义前向传播逻辑
        # 这里可以修改或添加额外的处理步骤
        outputs = super().forward(
            input_ids=input_ids,
            attention_mask=attention_mask,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
            lm_labels=lm_labels
        )
        return outputs

    def train(self, mode=True):
        # 自定义训练逻辑
        # 这里可以修改或添加额外的训练步骤
        super().train(mode)

# 创建自定义的T5模型实例
model = MyT5Model.from_pretrained('t5-base')
