from django.db import models
from django.contrib.auth.models import User
import os
from django.conf import settings
import json
import logging
from datetime import datetime
import numpy as np
from django.db import transaction
from shutil import rmtree
import struct
import re
from django.contrib import admin
from django.db.models.signals import pre_delete
from django.db import models
from django.dispatch import receiver


class Dataset(models.Model):
    name = models.CharField('Name', max_length=50)
    text_id = models.TextField(unique=True, null=False)
    description = models.TextField('Description')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=False, default=0)
    terms_count = models.IntegerField(default=0)
    documents_count = models.IntegerField(default=0)
    modalities_count = models.IntegerField(default=0)
    creation_time = models.DateTimeField(null=False, default=datetime.now)
    # 0=OK, 1=processing, 2=error
    status = models.IntegerField(null=False, default=0)
    error_message = models.TextField(null=True)
    language = models.TextField(null=False, default="english")

    preprocessing_params = models.TextField(null=False, default="{}")
    time_provided = models.BooleanField(null=False, default=True)
    is_public = models.BooleanField(null=False, default=True)

    def __str__(self):
        return self.name

    def reload(self):
        self.prepare_log()
        self.log("Loading dataset " + self.text_id + "...")

        Term.objects.filter(dataset=self).delete()
        Document.objects.filter(dataset=self).delete()
        Modality.objects.filter(dataset=self).delete()
        from models.models import ArtmModel
        ArtmModel.objects.filter(dataset=self).delete()

        try:
            meta_file = os.path.join(self.get_folder(), "meta", "meta.json")
            with open(meta_file) as f:
                self.docs_info = json.load(f)
        except BaseException as ex:
            self.log("WARNING! Wasn't able to load meta.json")
            self.log(str(ex))
            self.time_provided = False
            self.docs_info = {}

        try:
            preprocessing_params = json.loads(self.preprocessing_params)
            self.log("Preprocessing params:" + str(preprocessing_params))
        except BaseException:
            preprocessing_params = {}
            self.log("Warning! Failed to load preprocessing parameters.")

        # Preprocessing
        custom_vocab = False
        if "parse" in preprocessing_params:
            self.preprocess_parse(preprocessing_params["parse"])
        if "filter" in preprocessing_params:
            self.preprocess_filter(preprocessing_params["filter"])
            custom_vocab = True
        if "custom_vocab" in preprocessing_params and preprocessing_params[
                "custom_vocab"]:
            self.log("Will use custom vocab.txt")
            custom_vocab = True

        self.create_batches()
        self.gather_dictionary(custom_vocab=custom_vocab)
        self.load_documents()

        self.log("Loaded " + str(self.documents_count) + " documents.")

        # Creating folder for models
        model_path = os.path.join(
            settings.DATA_DIR, "datasets", self.text_id, "models")
        if not os.path.exists(model_path):
            os.makedirs(model_path)

        self.log("Dataset " + self.text_id + " loaded.")
        self.creation_time = datetime.now()
        self.status = 0
        self.save()

        # Counting weights for terms.
        self.log("Counting weights for terms.")
        self.reset_terms_weights()

    def preprocess_parse(self, params):
        self.log("Parsing documents...")
        from algo.preprocessing.Parser import Parser
        parser = Parser(self.get_folder())
        if "store_order" in params:
            parser.store_order = params["store_order"]
        if "hashtags" in params:
            parser.hashtags = params["hashtags"]
        if "bigrams" in params:
            parser.bigrams = params["bigrams"]
        self.log("Parsing initialized.")
        parser.process()
        self.log("Parsing done.")

    def preprocess_filter(self, params):
        from algo.preprocessing.VocabFilter import VocabFilter
        self.log("Filtering words...")
        filter = VocabFilter(os.path.join(self.get_folder(), "vw.txt"))
        self.log("Filtering initilized.")
        if "lower_bound" in params:
            filter.lower_bound = int(params["lower_bound"])
        if "upper_bound" in params:
            filter.upper_bound = int(params["upper_bound"])
        if "upper_bound_relative" in params:
            filter.upper_bound_relative = int(params["upper_bound_relative"])
        if "minimal_length" in params:
            filter.minimal_length = int(params["minimal_length"])
        filter.save_vocabulary(os.path.join(self.get_folder(), "vocab.txt"))
        self.log("Filtering done.")

    def create_batches(self):
        import artm

        self.log("Creating ARTM batches...")
        batches_folder = os.path.join(self.get_folder(), "batches")
        if os.path.exists(batches_folder):
            rmtree(batches_folder)
        os.makedirs(batches_folder)

        vw_path = os.path.join(self.get_folder(), "vw.txt")
        if not os.path.exists(vw_path):
            raise ValueError("FATAL ERROR! vw.txt file wasn't found.")

        batch_vectorizer = artm.BatchVectorizer(
            data_path=vw_path,
            data_format="vowpal_wabbit",
            batch_size=10000,
            collection_name=self.text_id,
            target_folder=batches_folder
        )
        self.log("Batches created.")

    @transaction.atomic
    def gather_dictionary(self, custom_vocab=False):
        import artm

        self.log("Creating ARTM dictionary...")
        dictionary = artm.Dictionary(name="dictionary")
        batches_folder = os.path.join(self.get_folder(), "batches")
        vocab_file_path = os.path.join(self.get_folder(), "vocab.txt")
        if custom_vocab:
            dictionary.gather(batches_folder, vocab_file_path=vocab_file_path)
        else:
            dictionary.gather(batches_folder)
            vocab_file = open(vocab_file_path, "w", encoding="utf-8")
        dictionary_file_name = os.path.join(
            self.get_folder(), "batches", "dictionary.txt")
        dictionary.save_text(dictionary_file_name)

        self.log("Saving terms to database...")
        term_index_id = -3
        self.modalities_count = 0
        self.terms_index = dict()
        modalities_index = dict()
        with open(dictionary_file_name, "r", encoding='utf-8') as f:
            for line in f:
                term_index_id += 1
                if term_index_id < 0:
                    continue
                parsed = line.replace(',', ' ').split()
                term = Term()
                term.dataset = self
                term.text = parsed[0]
                term.index_id = term_index_id
                term.token_value = float(parsed[2])
                term.token_tf = int(parsed[3].split('.')[0])
                term.token_df = int(parsed[4].split('.')[0])
                modality_name = parsed[1]
                if modality_name not in modalities_index:
                    modality = Modality()
                    modality.index_id = self.modalities_count
                    self.modalities_count += 1
                    modality.name = modality_name
                    modality.dataset = self
                    modality.save()
                    modalities_index[modality_name] = modality
                modality = modalities_index[modality_name]
                term.modality = modality
                modality.terms_count += 1

                term.save()

                if not custom_vocab:
                    vocab_file.write("%s %s\n" % (parsed[0], parsed[1]))

                self.terms_index[term.text] = term
                self.terms_index[term.text + "$#" + term.modality.name] = term
                self.terms_index[term.index_id] = term

                if term_index_id % 10000 == 0:
                    self.log(str(term_index_id))
                    # print(term_index_id)

        if not custom_vocab:
            vocab_file.close()

        self.terms_count = term_index_id + 1
        self.terms_count = term_index_id + 1

        self.log("Saving modalities...")
        max_modality_size = 0
        word_modality_id = -1
        for key, modality in modalities_index.items():
            if modality.terms_count > max_modality_size:
                word_modality_id = modality.id
                max_modality_size = modality.terms_count

        for key, modality in modalities_index.items():
            if modality.id == word_modality_id:
                modality.weight_spectrum = 1
                modality.weight_naming = 1
            if 'tag' in modality.name:
                modality.is_tag = True
            modality.save()

        self.normalize_modalities_weights()

    @transaction.atomic
    def load_documents(self):
        vw_file_name = os.path.join(self.get_folder(), "vw.txt")
        self.log(
            "Loading documents in Vowpal Wabbit format from " +
            vw_file_name)
        doc_id = 0
        with open(vw_file_name, "r", encoding="utf-8") as f:
            for line in f:
                if len(line) <= 1:
                    continue
                doc = Document()
                doc.dataset = self
                doc.index_id = doc_id
                doc.fetch_vw(line)
                if doc.text_id in self.docs_info:
                    doc.fetch_meta(self.docs_info[doc.text_id])
                doc.save()
                doc_id += 1
                if doc_id % 1000 == 0:
                    self.log(str(doc_id))

        self.documents_count = doc_id
        self.save()

    def reload_untrusted(self):
        try:
            self.reload()
        except BaseException:
            import traceback
            self.error_message = traceback.format_exc()
            self.status = 2
            self.save()

    def upload_from_archive(self, archive):
        archive_name = str(archive)
        parsed = archive_name.split('.')
        if parsed[1] != 'zip':
            raise ValueError("Must be zip archive")
        self.text_id = parsed[0]
        self.name = parsed[0]
        self.prepare_log("Loading dataset %s from archive..." % self.text_id)

        if len(Dataset.objects.filter(text_id=parsed[0])) != 0:
            raise ValueError("Dataset " + parsed[0] + " already exists.")
        zip_file_name = os.path.join(self.get_folder(), archive_name)
        with open(os.path.join(self.get_folder(), archive_name), 'wb+') as f:
            for chunk in archive.chunks():
                f.write(chunk)
        self.log("Archive uploaded.")

        import zipfile
        zip_ref = zipfile.ZipFile(zip_file_name, 'r')
        zip_ref.extractall(self.get_folder())
        zip_ref.close()
        self.log("Archive unpacked. Dataset name: " + self.text_id)

        os.remove(zip_file_name)

    def get_batches(self):
        import artm

        dataset_path = os.path.join(
            settings.DATA_DIR, "datasets", self.text_id)
        batches_folder = os.path.join(dataset_path, "batches")
        dictionary_file_name = os.path.join(batches_folder, "dictionary.txt")

        batch_vectorizer = artm.BatchVectorizer(
            data_path=batches_folder, data_format="batches")
        dictionary = artm.Dictionary(name="dictionary")
        dictionary.load_text(dictionary_file_name)
        return batch_vectorizer, dictionary

    def objects_safe(request):
        if request.user.is_anonymous():
            return Dataset.objects.filter(is_public=True)
        else:
            return Dataset.objects.filter(is_public=True) |\
                Dataset.objects.filter(is_public=False, owner=request.user)

    def prepare_log(self, string=""):
        self.log_file_name = os.path.join(self.get_folder(), "log.txt")
        with open(self.log_file_name, "w") as f:
            f.write("%s<br>\n" % string)

    def log(self, string):
        if settings.DEBUG:
            print(string)
        if settings.THREADING:
            with open(self.log_file_name, "a") as f:
                f.write(string + "<br>\n")

    def read_log(self):
        try:
            log_file_name = os.path.join(
                settings.DATA_DIR, "datasets", self.text_id, "log.txt")
            with open(log_file_name, "r") as f:
                return f.read()
        except BaseException:
            return "Datased is reloading"

    def get_folder(self):
        path = os.path.join(settings.DATA_DIR, "datasets", self.text_id)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def get_terms_index(self, modality=None):
        terms_index = dict()

        if modality:
            query_set = Term.objects.filter(dataset=self, modality=modality)
        else:
            query_set = Term.objects.filter(
                dataset=self).order_by("-modality__weight_naming")

        for term in query_set:
            terms_index[term.text] = term.index_id
            # terms_index[term.text + "#$" + term.modality.name] =
            # term.index_id
        return terms_index

    def check_terms_order(self, index, full=True):
        if self.terms_count != len(index):
            return False
        if full:
            for term in Term.objects.filter(dataset=self):
                if index[term.index_id] != term.text:
                    return False
        else:
            import random
            for i in range(10):
                term_iid = random.randint(0, self.terms_count - 1)
                if index[term_iid] != Term.objects.get(
                        dataset_id=self.id, index_id=term_iid).text:
                    return False
        return True

    @transaction.atomic
    def normalize_modalities_weights(self):
        weight_naming_sum = 0
        weight_spectrum_sum = 0

        modalities = Modality.objects.filter(dataset=self)

        wn = Dataset.normalize_weights([m.weight_naming for m in modalities])
        ws = Dataset.normalize_weights([m.weight_spectrum for m in modalities])

        for i in range(len(modalities)):
            modality = modalities[i]
            modality.weight_naming = wn[i]
            modality.weight_spectrum = ws[i]
            modality.save()

    def normalize_weights(w):
        s = sum(w)
        if s == 0:
            w[0] = 1
            return w
        w = [int((x / s) * 1000) for x in w]
        w[0] += (1000 - sum(w))
        return [x / 1000 for x in w]

    def get_dataset(request, modify=False):
        if "dataset_id" in request.GET:
            dataset = Dataset.objects.get(id=request.GET['dataset_id'])
        elif "ds" in request.GET:
            dataset = Dataset.objects.get(id=request.GET['ds'])
        elif "dataset" in request.GET:
            dataset = Dataset.objects.get(text_id=request.GET['dataset'])
        elif "dataset" in request.POST:
            dataset = Dataset.objects.get(text_id=request.POST['dataset'])
        else:
            return None

        if ((modify or not dataset.is_public)
                and not dataset.owner == request.user):
            return None
        return dataset

    # Returns array of terms weights.
    # Note. Each modality has two weights: for distance counting (spectrum)
    # and for top terms ranking (naming). In some procedures those weights are
    # used. To speed up those procedures, we count all weights for terms once
    # in reset_terms_weights and store in file. This function just read
    # corresonding array from file.
    def get_terms_weights(self, mode):
        if not os.path.exists(os.path.join(
                self.get_folder(), "terms_weights")):
            self.reset_terms_weights()

        if mode == "spectrum":
            return np.load(os.path.join(self.get_folder(),
                                        "terms_weights", "spectrum.npy"))
        elif mode == "naming":
            return np.load(os.path.join(self.get_folder(),
                                        "terms_weights", "naming.npy"))

    # Counts weights for terms and stores them in file.
    def reset_terms_weights(self):
        folder = os.path.join(self.get_folder(), "terms_weights")
        if not os.path.exists(folder):
            os.makedirs(folder)

        weights_spectrum = np.zeros(self.terms_count)
        weights_naming = np.zeros(self.terms_count)

        for modality in Modality.objects.filter(dataset=self):
            ws = modality.weight_spectrum
            wn = modality.weight_naming
            for term in Term.objects.filter(modality=modality):
                weights_spectrum[term.index_id] = ws
                weights_naming[term.index_id] = wn

        np.save(os.path.join(folder, "spectrum.npy"), weights_spectrum)
        np.save(os.path.join(folder, "naming.npy"), weights_naming)

    def delete_cached_distances(self):
        from models.models import ArtmModel
        for model in ArtmModel.objects.filter(dataset=self):
            model.delete_cached_distances()

    def delete_unused_folders(self):
        from models.models import ArtmModel
        models_folder = os.path.join(self.get_folder(), "models")
        legit_models = set([
            model.text_id
            for model
            in ArtmModel.objects.filter(dataset=self)
        ])
        for folder in os.listdir(models_folder):
            if folder not in legit_models:
                folder_to_remove = os.path.join(models_folder, folder)
                print("Removing trash: %s" % folder_to_remove)
                rmtree(folder_to_remove)

    def get_modalities_mask(self):
        path = os.path.join(self.get_folder(), "modalities_mask.npy")
        if os.path.exists(path):
            return np.load(path)
        else:
            ans = np.zeros(self.terms_count, dtype=np.int32)
            i = 0
            for term in Term.objects.filter(dataset=self):
                ans[i] = term.modality.index_id
                i += 1
            np.save(path, ans)
            return ans


@receiver(pre_delete, sender=Dataset, dispatch_uid='dataset_delete_signal')
def remove_dataset_files(sender, instance, using, **kwargs):
    folder = instance.get_folder()
    print("Will delete folder " + folder)
    try:
        rmtree(folder)
    except BaseException:
        pass


def on_start():
    '''
    for dataset in Dataset.objects.all():
        try:
            dataset.delete_unused_folders()
        except:
            pass
    '''

    for dataset in Dataset.objects.filter(status=1):
        dataset.status = 2
        dataset.error_message = "Dataset processing was interrupted."
        dataset.save()


class Document(models.Model):
    # Title of the document.
    title = models.TextField(null=False)

    # Link to the document on the Internet.
    url = models.URLField(null=True)

    # Short description of the document.
    snippet = models.TextField(null=True)

    # Time of publicaton.
    time = models.DateTimeField(null=True)

    # Id inside dataset.
    index_id = models.IntegerField(null=False)

    # Should coincide with relative path of text file, if available.
    text_id = models.TextField(null=True)

    # Dataset, to which this document belongs.
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=False)

    # [4 bytes term.index_id][2 bytes count][1 byte modality.index_id]
    bag_of_words = models.BinaryField(null=True)

    # Number of terms.
    terms_count = models.IntegerField(null=False, default=0)

    # Number of unique terms.
    unique_terms_count = models.IntegerField(null=False, default=0)

    # Full text of document.
    text = models.TextField(null=True)

    # [4 bytes position][1 byte length][4 bytes term.index_id]
    word_index = models.BinaryField(null=True)

    class Meta:
        # index_id's should be unique inside datasets.
        unique_together = (("dataset", "index_id"))

    # Extracts metatdata from doc_info object and saves it inside self.
    # To be used when dataset is loaded from archive.
    def fetch_meta(self, doc_info):
        if 'title' in doc_info:
            self.title = doc_info["title"]

        if "snippet" in doc_info:
            self.snippet = doc_info["snippet"]

        if "url" in doc_info:
            self.url = doc_info["url"]

        if "time" in doc_info:
            lst = doc_info["time"]
            try:
                self.time = datetime.fromtimestamp(lst)
            except BaseException:
                self.time = datetime(lst[0], lst[1], lst[2],
                                     lst[3], lst[4], lst[5])
        else:
            if self.dataset.time_provided:
                self.dataset.log("Warning! Time isn't provided.")
                self.dataset.time_provided = False

    # Extracts document from it's Vowpal Wabbit description.
    def fetch_vw(self, line_vw):
        parsed_vw = line_vw.split()
        self.text_id = parsed_vw[0]
        self.title = self.text_id
        self.word_index = bytes()
        self.text = ""

        # Try load text and wordpos
        text_found = False
        text_file = os.path.join(
            self.dataset.get_folder(), "documents", self.text_id)
        if os.path.exists(text_file):
            text_found = True
            with open(text_file, "r", encoding="utf-8") as f2:
                self.text = f2.read()

            wordpos_file = os.path.join(
                self.dataset.get_folder(), "wordpos", self.text_id)
            if os.path.exists(wordpos_file):
                word_index_list = []
                with open(wordpos_file, "r", encoding="utf-8") as f2:
                    for line in f2.readlines():
                        parsed = line.split()
                        if len(parsed) < 3:
                            continue
                        key = parsed[2]
                        if key in self.dataset.terms_index:
                            term_iid = self.dataset.terms_index[key].index_id
                            word_index_list.append(
                                (int(parsed[0]), -int(parsed[1]), term_iid))
                word_index_list.sort()
                self.word_index = bytes()
                for pos, length, tid in word_index_list:
                    self.word_index += struct.pack('I', pos) + struct.pack(
                        'B', -length) + struct.pack('I', tid)
            else:
                self.dataset.log(
                    "WARNING! No wordpos for file " + self.text_id)

        bow = BagOfWords()
        current_modality = '@default_class'
        for term in parsed_vw[1:]:
            if term[0] == '|':
                current_modality = term[1:]
            else:
                parsed_term = term.split(':')
                key = parsed_term[0] + "$#" + current_modality
                if ':' in term:
                    count = int(float(parsed_term[1]))
                else:
                    count = 1
                try:
                    term_index_id = self.dataset.terms_index[key].index_id
                    self.terms_count += count
                    bow.add_term(term_index_id, count)
                    if not text_found:
                        self.word_index += \
                            struct.pack('I', len(self.text)) + \
                            struct.pack('B', len(parsed_term[0])) + \
                            struct.pack('I', term_index_id)
                except BaseException:
                    pass
            if not text_found:
                self.text += term + " "
        self.bag_of_words = bow.to_bytes(self.dataset.terms_index)
        self.unique_terms_count = len(self.bag_of_words) // 7

    def objects_safe(request):
        if request.user.is_anonymous():
            return Document.objects.filter(dataset__is_public=True)
        else:
            return (Document.objects.filter(dataset__is_public=True) |
                    Document.objects.filter(
                    dataset__is_public=False, dataset__owner=request.user))

    def count_term(self, iid):
        bow = self.bag_of_words
        left = 0
        right = len(bow) // 7
        if right == 0:
            return 0
        while True:
            pos = (left + right) // 2
            bow_iid = struct.unpack('I', bow[7 * pos: 7 * pos + 4])[0]
            if bow_iid == iid:
                return struct.unpack('H', bow[7 * pos + 4: 7 * pos + 6])[0]
            elif bow_iid > iid:
                right = pos
            else:
                left = pos + 1
            if left >= right:
                return 0

    def fetch_tags(self):
        tag_modalities = Modality.objects.filter(
            dataset=self.dataset, is_tag=True)
        if len(tag_modalities) == 0:
            return []

        tag_names = dict()
        tag_strings = dict()

        for modality in tag_modalities:
            tag_names[modality.index_id] = modality.name

        bow = self.bag_of_words
        unique_terms_count = len(bow) // 7

        for i in range(unique_terms_count):
            bow_iid = struct.unpack('I', bow[7 * i: 7 * i + 4])[0]
            modality_iid = struct.unpack('B', bow[7 * i + 6: 7 * i + 7])[0]
            if modality_iid in tag_names:
                term = Term.objects.filter(
                    dataset=self.dataset, index_id=bow_iid)[0]
                if modality_iid in tag_strings:
                    tag_strings[modality_iid] += ', '
                else:
                    tag_strings[modality_iid] = ''
                tag_strings[modality_iid] += '<a href="/term?id=' + \
                    str(term.id) + '">' + term.text + '</a>'

        ret = []
        for tag_id, tag_string in tag_strings.items():
            ret.append({"name": tag_names[tag_id], "string": tag_string})
        return ret

    # Returns set of index_id's of words in this document which are modlities.
    def get_tags_ids(self):
        tag_ids = set()
        ret = set()
        for modality in Modality.objects.filter(
                dataset=self.dataset, is_tag=True):
            tag_ids.add(modality.index_id)
        bow = self.bag_of_words
        for i in range(len(bow) // 7):
            modality_iid = struct.unpack('B', bow[7 * i + 6: 7 * i + 7])[0]
            if modality_iid in tag_ids:
                ret.add(struct.unpack('I', bow[7 * i: 7 * i + 4])[0])
        return ret

    def fetch_bow(self, cut_bow):
        bow = self.bag_of_words
        unique_terms_count = len(bow) // 7
        bow_entries = []
        for i in range(unique_terms_count):
            bow_iid = struct.unpack('I', bow[7 * i: 7 * i + 4])[0]
            bow_count = struct.unpack('H', bow[7 * i + 4: 7 * i + 6])[0]
            bow_entries.append((-bow_count, bow_iid))
        bow_entries.sort()
        bow_send = ""
        prfx = "<a href = '/term?ds=" + str(self.dataset.id) + "&iid="
        rest = unique_terms_count
        for x in bow_entries:
            cnt = -x[0]
            iid = x[1]
            if cnt <= cut_bow:
                bow_send += str(rest) + " terms, which occured " + \
                    str(cut_bow) + " times or less, aren't shown."
                break
            bow_send += prfx + str(iid) + "'>" + \
                Term.objects.filter(dataset=self.dataset,
                                    index_id=iid)[0].text + \
                "</a>: " + str(cnt) + "<br>"
            rest -= 1

        return bow_send

    def get_text(self):
        return self.text

    # Returns positions of terms as list of triples:
    #     (position, length, term.index_id).
    def get_word_index(self, no_overlap=True):
        wi = self.word_index
        if wi is None:
            return None

        count = len(wi) // 9
        last_pos = -1
        ret = []
        for i in range(count):
            pos = struct.unpack('I', wi[9 * i: 9 * i + 4])[0]
            length = struct.unpack('B', wi[9 * i + 4: 9 * i + 5])[0]
            if no_overlap:
                if pos < last_pos:
                    continue
                else:
                    last_pos = pos + length
            ret.append((pos, length, struct.unpack(
                'I', wi[9 * i + 5: 9 * i + 9])[0]))

        return ret

    def get_concordance(self, terms):
        text = self.text
        wi = self.word_index
        conc = ""
        cur_pos = 0
        for i in range(len(wi) // 9):
            term_index_id = struct.unpack('I', wi[9 * i + 5: 9 * i + 9])[0]
            if term_index_id in terms:
                pos = struct.unpack('I', wi[9 * i: 9 * i + 4])[0]
                length = struct.unpack('B', wi[9 * i + 4: 9 * i + 5])[0]
                conc += text[cur_pos: pos] + "<b>" + \
                    text[pos: pos + length] + "</b>"
                cur_pos = pos + length
        conc += text[cur_pos:]
        sentences = filter(None, re.split("[!?.\n]+", conc))
        conc = ""
        ctr = 0
        for sentence in sentences:
            if "</b>" in sentence:
                ctr += 1
                if ctr == 10:
                    conc += "<i>(Not all occurences are shown)</i><br>"
                    break
                length = len(sentence)
                pref = ""
                suf = "."
                fi = sentence.find("<b>") - 60
                li = sentence.find("</b>") + 60
                if fi < 0:
                    fi = 0
                else:
                    while(fi != 0 and sentence[fi] != ' '):
                        fi -= 1
                    pref = "... "

                if li > length:
                    li = length
                else:
                    while(li < length and sentence[li] != ' '):
                        li += 1
                    suf = " ..."

                conc += pref + sentence[fi: li] + suf + "<br>"

        return conc[:-4]
        return conc[:-4]

    def __str__(self):
        return self.title


class Modality(models.Model):
    name = models.TextField(null=False)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=False)
    terms_count = models.IntegerField(null=False, default=0)
    index_id = models.IntegerField(null=False, default=0)
    is_tag = models.BooleanField(null=False, default=False)

    weight_naming = models.FloatField(null=False, default=0)
    weight_spectrum = models.FloatField(null=False, default=0)

    def __str__(self):
        return self.dataset.name + "/" + self.name


class Term(models.Model):
    text = models.TextField(null=False)
    modality = models.ForeignKey(Modality, on_delete=models.CASCADE, null=False)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=False)
    # id in UCI files and word_index files
    index_id = models.IntegerField(null=False)
    token_value = models.FloatField(default=0)
    token_tf = models.IntegerField(default=0)
    token_df = models.IntegerField(default=0)
    documents = models.BinaryField(null=True)
    documents_defined = models.BooleanField(default=False)

    def __str__(self):
        return self.text

    def count_documents_index(self):
        if self.documents_defined:
            return
        self.documents_defined = True
        self.save()
        relations = []
        documents = Document.objects.filter(dataset=self.dataset)

        temp_count = 0

        self.documents = bytes()
        for document in documents:
            count = document.count_term(self.index_id)
            if count != 0:
                relations.append((count, document.index_id))
                if temp_count < 5:
                    self.documents += struct.pack('I', document.index_id) + \
                        struct.pack('H', count)
                    temp_count += 1
                    self.save()

        relations.sort(reverse=True)

        self.documents = bytes()
        for count, document_index_id in relations:
            self.documents += struct.pack('I', document_index_id) + \
                struct.pack('H', count)

        self.save()

    def get_documents(self):
        self.count_documents_index()
        for i in range(len(self.documents) // 6):
            doc_iid = struct.unpack('I', self.documents[6 * i: 6 * i + 4])[0]
            yield Document.objects.get(dataset_id=self.dataset_id,
                                       index_id=doc_iid)

    def objects_safe(request):
        if request.user.is_anonymous():
            return Term.objects.filter(dataset__is_public=True)
        return (Term.objects.filter(dataset__is_public=True) |
                Term.objects.filter(dataset__is_public=False,
                                    dataset__owner=request.user))


admin.site.register(Dataset)
admin.site.register(Document)
admin.site.register(Modality)
admin.site.register(Term)


class BagOfWords():
    """Helper class to pack bags of words into binary"""
    def __init__(self):
        self.bow = dict()

    def add_term(self, word_id, count):
        if word_id not in self.bow:
            self.bow[word_id] = count
        else:
            self.bow[word_id] += count

    def to_bytes(self, terms_index):
        ret = bytes()
        for word_id, count in sorted(self.bow.items()):
            ret += struct.pack('I', word_id) + struct.pack('H', count) + \
                struct.pack('B', terms_index[word_id].modality.index_id)
        return ret
