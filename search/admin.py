from django import forms
from search.models import *
from django.contrib import admin
import datetime
# django 1.4 only
# from django.utils.timezone import utc
import csv
from django.db import connections
from decimal import *
from django.db import IntegrityError
from django.contrib import messages
from django.db import transaction

class BulkUploadForm(forms.ModelForm):
    file_to_import = forms.FileField()
    import_options = (
        ('Individuals','Individuals'),
        ('Phenotypes','Phenotypes'),
        ('Samples','Samples'),
        ('Sources','Sources')
    )
    import_data_type = forms.ChoiceField(import_options)

    class Meta:
        model = BulkUpload

class BulkUploadAdmin(admin.ModelAdmin):
    
    form = BulkUploadForm
    true_list = ["Yes", "yes", "true", "True", "1", "Affected", "affected"]
    false_list = ["No", "no", "false", "False", "0", "Unaffected", "unaffected"]
    
    #Overrides model object saving.
    def save_model(self, request, obj, form, change):
        records = csv.DictReader(request.FILES["file_to_import"])
        import_data_type = request.POST["import_data_type"]
        warehouseCursor = connections['warehouse'].cursor()
        for line in records:
        
            if import_data_type == "Individuals":
                ## required columns: Centre,Centre ID                
                try:
                    centre = line['Centre']
                    centre_id = line['Centre ID']                    
                except KeyError:
                    messages.error(request, u"Input file is missing required column(s) 'Centre,Centre ID'")
                    return     
                
                try:
                    source = Source.objects.get(source_name=centre)
                except Source.DoesNotExist:
                    messages.error(request, u"Can't find source in database '" + centre + u"'")
                    continue
                               
                ## check if the id has already been entered for the given source
                if IndividualIdentifier.objects.filter(individual_string=centre_id,source_id=source.id).count() > 0:
                    messages.error(request, u"Individual '" + centre_id + u"' already added for this source")
                    continue
                
                ## an empty active_id field means that the object refers to itself!
                ## if the active_id field is not empty, that means it refers to another individual object
                ind = Individual()                
                ind.date_created = datetime.datetime.now()
                ind.last_updated = datetime.datetime.now()
                ind.save()                    
                
                ## create the phenodb_id
                pdbId = PhenodbIdentifier()
                pdbId.individual = ind
                pdbId.phenodb_id = u"pdb" + str(ind.pk)
                pdbId.date_created = datetime.datetime.now()
                pdbId.last_updated = datetime.datetime.now()
                pdbId.save()
                
                try:
                    collection = line['Collection']
                    coll = Collection.objects.get(collection_name=collection)
                except Collection.DoesNotExist:
                    messages.error(request, u"Can't find collection in database '" + collection + u"'")
                    collection = None
                except KeyError:
                    collection = None
                    
                if collection is not None:
                    indColl = IndividualCollection()
                    indColl.individual = ind
                    indColl.collection = coll
                    indColl.date_created = datetime.datetime.now()
                    indColl.last_updated = datetime.datetime.now()
                    indColl.save()
                      
                ## insert the individual identifier
                indId = IndividualIdentifier()
                indId.individual = ind
                indId.individual_string = centre_id                
                indId.source = source
                indId.date_created = datetime.datetime.now()
                indId.last_updated = datetime.datetime.now()                
                try:
                    indId.save()
                except IntegrityError:
                    messages.error(request, u"Individual ID " + centre_id + " is already in the database")
                    continue
                                        
                ## insert phenotype values
                for col in line:                      
                    try:   
                        if len(line[col]) == 0:
                            continue
                    except TypeError:
                        ## vale is None
                        continue
                                   
                    try:
                        pheno = Phenotype.objects.get(phenotype_name=col)
                    except Phenotype.DoesNotExist:
#                        messages.error(request, u"Warning Can't find phenotype '" + col + "' in database")
                        continue
                    
                    if pheno.phenotype_type.phenotype_type == u"Affection Status":
                        affectVal = AffectionStatusPhenotypeValue()
                        affectVal.phenotype = pheno
                        affectVal.individual = ind
                        ## if the value is empty or no set as false
                        if line[col] in BulkUploadAdmin.false_list:
                            affectVal.phenotype_value = False
                        elif line[col] in BulkUploadAdmin.true_list:
                            affectVal.phenotype_value = True
                        else:
                            continue
                        affectVal.flagged = False
                        affectVal.date_created = datetime.datetime.now()
                        affectVal.last_updated = datetime.datetime.now()
                        try:
                            affectVal.save()
                        except:
                            messages.error(request, u"failed to save " + pheno.phenotype_name)           
                    elif pheno.phenotype_type.phenotype_type == u"Qualitative":
                        qualVal = QualitativePhenotypeValue()
                        qualVal.phenotype = pheno
                        qualVal.individual = ind
                        qualVal.phenotype_value = line[col].strip()
                        qualVal.flagged = False
                        qualVal.date_created = datetime.datetime.now()
                        qualVal.last_updated = datetime.datetime.now()
                        try:
                            qualVal.save()
                        except:
                            messages.error(request, u"failed to save " + pheno.phenotype_name)
                    elif pheno.phenotype_type.phenotype_type == u"Quantitative":
                        quantVal = QuantitiatvePhenotypeValue()
                        quantVal.phenotype = pheno
                        quantVal.individual = ind
                        if str.isdigit(line[col]) == False:
                            continue
                        quantVal.phenotype_value = Decimal(line[col])                            
                        quantVal.flagged = False
                        quantVal.date_created = datetime.datetime.now()
                        quantVal.last_updated = datetime.datetime.now()
                        try:
                            quantVal.save()
                        except:
                            messages.error(request, u"failed to save " + pheno.phenotype_name)
                    else:
                        messages.error(request, u"unrecognised phenotype type " + pheno.phenotype_type.phenotype_type)
                        
                    transaction.commit()
            
            elif import_data_type == "Phenotypes":
                ## required columns: Name,Type,Description
                ## check if the required columns are in the file otherwise die explaining required format
                try:
                    phenoType = PhenotypeType.objects.get(phenotype_type=line['Type'])
                except PhenotypeType.DoesNotExist:
                    messages.error(request, u"Phenotype Type " + line['Type'] + u" was NOT found in phenodb for " + line['Name'])
                    continue
                         
                pheno = Phenotype()
                pheno.phenotype_name = line['Name']
                pheno.phenotype_type = phenoType
                pheno.phenotype_description = line['Description']
                try:
                    pheno.save()
                except IntegrityError:
                    messages.error(request, u"Phenotype " + line['Name'] + " is already in the database")
                    continue
                messages.success(request, u"Phenotype " + line['Name'] + u" was added to PhenoDB")
                
            elif import_data_type == "Sources":
                ## required columns: Name,Contact,Description
                ## check if the required columns are in the file otherwise die explaining required format
                source = Source()
                source.source_name = line['Centre']
                source.contact_name = line['Contact']
                source.source_description = line['Description']
                try:
                    source.save()
                except IntegrityError:
                    messages.error(request, u"Source " + line['Centre'] + " is already in the database")
                    continue
                messages.success(request, u"Source " + line['Centre'] + u" was added to PhenoDB")
                    
            elif import_data_type == "Samples":
                ## required columns: Centre,Centre ID,Sample ID                
                try:
                    centre = line['Centre']
                    centre_id = line['Centre ID']
                    sample_id = line['Sample ID']                    
                except KeyError:
                    messages.error(request, u"Input file is missing required column(s) 'Centre,Centre ID,Sample ID'")
                    return     
                
                try:
                    source = Source.objects.get(source_name=centre)
                except Source.DoesNotExist:
                    messages.error(request, u"Can't find source in database '" + centre + u"'")
                    continue                
                
                ## get the individual id
                
                ## check that a sample has not already been entered for the ind with the same name
                
                ## check if the id has already been entered for the given source
                try:
                    sampleIndId = IndividualIdentifier.objects.get(individual_string=centre_id,source_id=source.id)
                except IndividualIdentifier.DoesNotExist:
                    messages.error(request, u"Individual " + centre_id + u" NOT found in phenodb")
                    continue
                
                if Sample.objects.filter(individual=sampleIndId.individual,sample_id=sample_id).count() > 0:
                    messages.error(request, u"Sample ID '" + sample_id + u"' already added for this individual")
                    continue
                          
                sample = Sample()
                sample.individual = sampleIndId.individual
                sample.sample_id = sample_id
                sample.date_created = datetime.datetime.now()
                sample.last_updated = datetime.datetime.now()
                
                warehouseCursor.execute("SELECT DISTINCT sanger_sample_id, supplier_name, gender FROM samples WHERE name = %s ORDER BY checked_at desc", sample.sample_id)
                row = warehouseCursor.fetchone()
                if row is None:
                    messages.error(request, u"Sample " + sample.sample_id + u" NOT found in warehouse")
                    continue
                if row[0] is None:
                    messages.error(request, u"Sample " + sample.sample_id + u" NOT found in warehouse")
                    continue  
                if row[1] != sampleIndId.individual_string:
                    messages.error(request, u"supplier name " + str(sampleIndId.individual_string) + u" does not match warehouse "  + row[1])
                    try:
                        source = Source.objects.get(source_name=centre)
                    except Source.DoesNotExist:
                        continue
                    ## insert the new individual identifier
                    indId = IndividualIdentifier()
                    indId.individual = sampleIndId.individual
                    indId.individual_string = row[1]
                    indId.source = source
                    indId.date_created = datetime.datetime.now()
                    indId.last_updated = datetime.datetime.now()
                    try:
                        indId.save()
                    except IntegrityError:
                        messages.error(request, u"Individual ID " + row[1] + " is already in the database")
                        continue                                                               
                try:
                    sample.save()
                except IntegrityError:
#                   messages.error(request, u"Sample " + sample_id + " is already in the database")
                    continue
                transaction.commit()
        return

class PlatformAdmin(admin.ModelAdmin):
    list_display = ('platform_name', 'platform_type', 'platform_description')

class PhenotypeAdmin(admin.ModelAdmin):
    list_display = ('phenotype_name', 'phenotype_type', 'phenotype_description')                     
                     
class StudyAdmin(admin.ModelAdmin):
    list_display = ('study_name', 'platform', 'study_description', 'data_location', 'last_updated')
    
class SourceAdmin(admin.ModelAdmin):
    list_display = ('source_name', 'contact_name', 'source_description')
    
class QCAdmin(admin.ModelAdmin):
    list_display = ('qc_name', 'qc_description', 'last_updated')
                          
admin.site.register(Platform, PlatformAdmin)
admin.site.register(PlatformType)
admin.site.register(PhenotypeType)
admin.site.register(Phenotype, PhenotypeAdmin)
admin.site.register(Study, StudyAdmin)
admin.site.register(Source, SourceAdmin)
admin.site.register(QC, QCAdmin)
admin.site.register(BulkUpload, BulkUploadAdmin)
admin.site.register(Collection)
